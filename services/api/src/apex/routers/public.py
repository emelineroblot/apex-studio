"""Espace client — routeur **dédié** et cloisonné (§3-L.3, J3).

Trois règles, structurelles plutôt que défensives :

1. **Une seule dépendance d'authentification** (`CurrentClient`) sur toutes les routes. Il
   n'existe aucun chemin vers ces données qui ne passe pas par une session client adossée
   à un lien de partage ni expiré ni révoqué.
2. **Aucun identifiant de collection, de client ou de shooting en paramètre.** Le périmètre
   vient du jeton, jamais de la requête. Les seuls identifiants acceptés sont des
   `media_id`, systématiquement validés contre `collection_item`.
3. **`404` hors périmètre, jamais `403`** : un client qui devine un `media_id` voisin ne
   doit pas pouvoir déduire qu'il existe.

Le HD n'est **jamais** servi ici : il ne sort que par l'archive ZIP, après validation de la
sélection (§3-H.3, §3-M).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from apex.config import settings
from apex.db import get_db
from apex.models.billing import ClientSelection, SelectionItem
from apex.models.collection import Collection, CollectionItem
from apex.models.media import Media
from apex.models.search import MediaSearch
from apex.pipeline.derivatives import watermark_encoded_image
from apex.routers._common import not_implemented
from apex.schemas.public import (
    PublicCollectionRef,
    PublicCollectionResponse,
    PublicDeliveryStatusResponse,
    PublicMediaItem,
    PublicSelectionItemResponse,
    PublicSelectionItemUpdate,
    PublicSelectionResponse,
    PublicSelectionValidateResponse,
    PublicSessionRequest,
    PublicSessionResponse,
)
from apex.security import ClientScope, CurrentClient, create_client_session_token
from apex.services import sharing
from apex.services.pagination import paginate_by_id
from apex.services.storage import ObjectNotFoundError, get_storage_client

router = APIRouter(tags=["public"])

#: Plafond de page. Une grille d'aperçus ne gagne rien à charger davantage d'un coup —
#: chaque vignette est une requête HTTP médiée par le backend.
MAX_PAGE_SIZE = 100


def _not_found() -> HTTPException:
    """Hors périmètre = introuvable. Jamais `403` : ce serait confirmer l'existence."""
    return HTTPException(
        status_code=404,
        detail={"code": "not_found", "message": "Ressource introuvable.", "detail": None},
    )


def _collection_ref(db: Session, collection: Collection) -> PublicCollectionRef:
    item_count = int(
        db.execute(
            select(func.count())
            .select_from(CollectionItem)
            .where(CollectionItem.collection_id == collection.id)
        ).scalar_one()
    )
    return PublicCollectionRef(
        title=collection.title,
        description=collection.description,
        item_count=item_count,
        studio_name=settings.studio_name,
    )


def _get_collection(db: Session, scope: ClientScope) -> Collection:
    collection = db.execute(
        select(Collection).where(Collection.id == scope.collection_id)
    ).scalar_one_or_none()
    if collection is None:
        raise _not_found()
    return collection


def _assert_in_scope(db: Session, scope: ClientScope, media_id: int) -> None:
    """Seul contrôle d'appartenance du routeur — un `EXISTS` sur la clé primaire de
    `collection_item`, donc constant quelle que soit la taille de la collection."""
    in_collection = db.execute(
        select(
            exists().where(
                CollectionItem.collection_id == scope.collection_id,
                CollectionItem.media_id == media_id,
            )
        )
    ).scalar_one()
    if not in_collection:
        raise _not_found()


def _selection(db: Session, collection_id: int) -> ClientSelection | None:
    return db.execute(
        select(ClientSelection).where(ClientSelection.collection_id == collection_id)
    ).scalar_one_or_none()


@router.post(
    "/session",
    response_model=PublicSessionResponse,
    summary="Échange du jeton long contre une session courte (30 min)",
    responses={410: {"description": 'Lien expiré ou révoqué — `{"code": "link_expired"}`'}},
)
def public_session(
    payload: PublicSessionRequest, db: Session = Depends(get_db)
) -> PublicSessionResponse:
    try:
        link = sharing.resolve_token(db, payload.token)
    except sharing.ShareLinkNotFound as exc:
        raise _not_found() from exc
    except sharing.ShareLinkExpired as exc:
        # Corps métier volontairement nu : la page « Ce lien n'est plus valide » doit
        # pouvoir s'afficher sans jamais montrer de trace technique (critère d'acceptation).
        raise HTTPException(
            status_code=410,
            detail={
                "code": "link_expired",
                "message": "Ce lien de partage n'est plus valide.",
                "detail": None,
            },
        ) from exc

    collection = db.execute(
        select(Collection).where(Collection.id == link.collection_id)
    ).scalar_one_or_none()
    if collection is None:
        raise _not_found()

    sharing.record_view(db, link)
    token, expires_in = create_client_session_token(link, collection.client_id)
    reference = _collection_ref(db, collection)
    db.commit()
    return PublicSessionResponse(access_token=token, expires_in=expires_in, collection=reference)


@router.get(
    "/collection",
    response_model=PublicCollectionResponse,
    summary="Aperçus filigranés de la collection du jeton",
)
def public_collection(
    scope: CurrentClient,
    cursor: str | None = None,
    limit: int = 50,
    selected_only: bool = False,
    db: Session = Depends(get_db),
) -> PublicCollectionResponse:
    collection = _get_collection(db, scope)
    selection = _selection(db, collection.id)

    stmt = (
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection.id)
        .join(Media, Media.id == CollectionItem.media_id)
        # Un média en quarantaine n'a pas d'aperçu exploitable : il n'a rien à faire sous
        # les yeux d'un client, même s'il a été ajouté à la collection par erreur.
        .where(Media.ingest_status != "quarantined")
    )
    if selected_only:
        if selection is None:
            return PublicCollectionResponse(
                collection=_collection_ref(db, collection), items=[], next_cursor=None
            )
        stmt = stmt.join(
            SelectionItem,
            (SelectionItem.media_id == CollectionItem.media_id)
            & (SelectionItem.selection_id == selection.id),
        )

    items, next_cursor, _ = paginate_by_id(
        db, stmt, CollectionItem.media_id, cursor=cursor, limit=min(limit, MAX_PAGE_SIZE)
    )
    media_ids = [item.media_id for item in items]

    # Deux lectures groupées plutôt qu'une par ligne. Les numéros de course viennent de la
    # projection de recherche (§3-K.1), jamais d'une jointure sur `media_engagement`.
    numbers: dict[int, list[str]] = {}
    shot_ats: dict[int, datetime | None] = {}
    if media_ids:
        for projection in db.execute(
            select(MediaSearch.media_id, MediaSearch.car_numbers, MediaSearch.shot_at).where(
                MediaSearch.media_id.in_(media_ids)
            )
        ):
            numbers[projection.media_id] = list(projection.car_numbers or [])
            shot_ats[projection.media_id] = projection.shot_at

    comments: dict[int, str | None] = {}
    if selection is not None and media_ids:
        for row in db.execute(
            select(SelectionItem.media_id, SelectionItem.comment).where(
                SelectionItem.selection_id == selection.id,
                SelectionItem.media_id.in_(media_ids),
            )
        ):
            comments[row.media_id] = row.comment

    entries: list[PublicMediaItem] = []
    for media_id in media_ids:
        shot_at = shot_ats.get(media_id)
        entries.append(
            PublicMediaItem(
                media_id=media_id,
                # Chemins relatifs au préfixe d'API, comme partout ailleurs dans le
                # contrat (`/media/{id}/file/thumb`) : le frontend les résout contre
                # `NEXT_PUBLIC_API_BASE_URL`. Une URL absolue construite ici serait
                # fausse derrière le proxy Vercel, qui ne transmet pas le schéma d'origine
                # à l'application ASGI.
                preview_url=f"/public/media/{media_id}/file/preview",
                thumb_url=f"/public/media/{media_id}/file/thumb",
                shot_at=shot_at.isoformat() if shot_at is not None else None,
                car_numbers=numbers.get(media_id, []),
                selected=media_id in comments,
                comment=comments.get(media_id),
            )
        )

    return PublicCollectionResponse(
        collection=_collection_ref(db, collection),
        items=entries,
        next_cursor=next_cursor,
    )


def _serve_variant(
    db: Session, scope: ClientScope, media_id: int, request: Request, *, variant: str
) -> Response:
    """Sert une variante filigranée.

    `preview` l'est déjà — filigrane cuit dans les pixels à l'ingestion. `thumb` ne l'est
    pas : la vignette stockée doit rester propre, pHash et netteté sont calculés dessus
    (`pipeline/derivatives.py::build_thumb`). Elle est donc filigranée **à la volée**, sur
    la copie servie, jamais sur celle qui est stockée — c'est exactement la piste retenue
    en revue J1 quand cet écart a été signalé et laissé ouvert pour J3.
    """
    _assert_in_scope(db, scope, media_id)
    media = db.execute(select(Media).where(Media.id == media_id)).scalar_one_or_none()
    if media is None:
        raise _not_found()

    storage_key = media.storage_key_preview if variant == "preview" else media.storage_key_thumb
    if storage_key is None:
        raise _not_found()

    # L'ETag porte la variante : sans ce suffixe, vignette et aperçu du même média
    # partageraient une empreinte et le navigateur servirait l'une pour l'autre.
    fingerprint = media.content_hash.hex() if media.content_hash else f"media-{media_id}"
    etag = f'"{fingerprint}-{variant}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    storage = get_storage_client()
    try:
        body = storage.open_stream(storage_key)
    except ObjectNotFoundError as exc:
        raise _not_found() from exc

    headers = {"ETag": etag, "Cache-Control": "private, max-age=3600"}
    if variant == "preview":
        headers["Content-Length"] = str(body.content_length)
        return StreamingResponse(body.chunks, media_type="image/webp", headers=headers)

    raw = b"".join(body.chunks)
    try:
        watermarked = watermark_encoded_image(raw, f"{settings.studio_name} - apercu")
    except OSError as exc:
        # Vignette illisible : l'espace client ne montre jamais de trace technique.
        raise _not_found() from exc
    headers["Content-Length"] = str(len(watermarked))
    return Response(content=watermarked, media_type="image/webp", headers=headers)


@router.get(
    "/media/{media_id}/file/preview",
    summary="Flux filigrané — `404` si le média est hors de la collection du jeton",
)
def public_media_preview(
    media_id: int, scope: CurrentClient, request: Request, db: Session = Depends(get_db)
) -> Response:
    return _serve_variant(db, scope, media_id, request, variant="preview")


@router.get(
    "/media/{media_id}/file/thumb",
    summary="Vignette filigranée à la volée — `404` hors de la collection du jeton",
)
def public_media_thumb(
    media_id: int, scope: CurrentClient, request: Request, db: Session = Depends(get_db)
) -> Response:
    return _serve_variant(db, scope, media_id, request, variant="thumb")


@router.put(
    "/selection/items/{media_id}",
    response_model=PublicSelectionItemResponse,
    summary="Sélectionner / commenter une photo — `409` si la sélection est déjà validée",
)
def put_selection_item(
    media_id: int, payload: PublicSelectionItemUpdate, scope: CurrentClient
) -> PublicSelectionItemResponse:
    not_implemented("PUT /public/selection/items/{media_id}")


@router.delete(
    "/selection/items/{media_id}",
    status_code=204,
    summary="Retirer une photo de la sélection",
)
def delete_selection_item(media_id: int, scope: CurrentClient) -> None:
    not_implemented("DELETE /public/selection/items/{media_id}")


@router.get(
    "/selection",
    response_model=PublicSelectionResponse,
    summary="Sélection courante",
)
def get_public_selection(scope: CurrentClient) -> PublicSelectionResponse:
    not_implemented("GET /public/selection")


@router.post(
    "/selection/validate",
    response_model=PublicSelectionValidateResponse,
    summary="Valider la sélection — déclenche `build_delivery` et `refresh_draft_invoice`",
)
def validate_selection(scope: CurrentClient) -> PublicSelectionValidateResponse:
    not_implemented("POST /public/selection/validate")


@router.get(
    "/delivery",
    response_model=PublicDeliveryStatusResponse,
    summary="État de la préparation de livraison",
)
def get_public_delivery(scope: CurrentClient) -> PublicDeliveryStatusResponse:
    not_implemented("GET /public/delivery")


@router.get(
    "/delivery/archive",
    summary="Flux ZIP — `403` si sélection non validée ou livraison non prête",
)
def get_public_delivery_archive(scope: CurrentClient) -> StreamingResponse:
    not_implemented("GET /public/delivery/archive")
