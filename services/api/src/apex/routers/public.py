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

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apex.config import settings
from apex.db import get_db
from apex.models.billing import ClientSelection, Delivery, SelectionItem
from apex.models.catalog import Client
from apex.models.collection import Collection, CollectionItem
from apex.models.media import Media
from apex.models.search import MediaSearch
from apex.pipeline.derivatives import watermark_encoded_image
from apex.queue.enqueue import enqueue
from apex.schemas.billing import SelectionStatus
from apex.schemas.public import (
    DeliveryReadiness,
    PublicCollectionRef,
    PublicCollectionResponse,
    PublicDeliveryRef,
    PublicDeliveryStatusResponse,
    PublicMediaItem,
    PublicSelectionItemResponse,
    PublicSelectionItemUpdate,
    PublicSelectionResponse,
    PublicSelectionSummaryItem,
    PublicSelectionValidateResponse,
    PublicSessionRequest,
    PublicSessionResponse,
)
from apex.security import ClientScope, CurrentClient, create_client_session_token
from apex.services import delivery as delivery_service
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


def _get_or_create_selection(db: Session, collection_id: int) -> ClientSelection:
    """La sélection naît au premier clic, pas à la création de la collection.

    Une ligne créée d'avance rendrait indiscernables « le client n'a pas encore ouvert la
    galerie » et « le client a tout décoché », deux situations que le studio doit
    distinguer pour savoir s'il faut relancer.
    """
    selection = _selection(db, collection_id)
    if selection is None:
        selection = ClientSelection(collection_id=collection_id, status="open")
        db.add(selection)
        db.flush()
    return selection


def _assert_selection_open(selection: ClientSelection) -> None:
    """Une sélection validée est **définitive** : elle a déclenché la préparation de la
    livraison et alimenté une facture brouillon. La rouvrir en silence désynchroniserait
    les trois. L'écran client prévient de cette irréversibilité avant de valider."""
    if selection.status == "validated":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "selection_validated",
                "message": "Votre sélection a été validée : elle ne peut plus être modifiée.",
                "detail": None,
            },
        )


def _delivery(db: Session, collection_id: int) -> Delivery | None:
    selection = _selection(db, collection_id)
    if selection is None:
        return None
    return db.execute(
        select(Delivery).where(Delivery.selection_id == selection.id)
    ).scalar_one_or_none()


def _delivery_forbidden(message: str) -> HTTPException:
    """`403` et non `404` : la ressource existe et le client y a droit — plus tard. Lui
    repondre « introuvable » l'enverrait chercher une erreur qui n'existe pas."""
    return HTTPException(
        status_code=403,
        detail={"code": "delivery_not_ready", "message": message, "detail": None},
    )


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
    media_id: int,
    payload: PublicSelectionItemUpdate,
    scope: CurrentClient,
    db: Session = Depends(get_db),
) -> PublicSelectionItemResponse:
    _assert_in_scope(db, scope, media_id)
    selection = _get_or_create_selection(db, scope.collection_id)
    _assert_selection_open(selection)

    # Idempotent (§3-E.6, même principe que la file) : re-cocher une photo déjà cochée met
    # à jour son commentaire sans dupliquer la ligne. L'UI enregistre de façon optimiste et
    # peut légitimement rejouer une requête.
    comment = (payload.comment or "").strip() or None
    db.execute(
        pg_insert(SelectionItem)
        .values(selection_id=selection.id, media_id=media_id, comment=comment)
        .on_conflict_do_update(
            index_elements=[SelectionItem.selection_id, SelectionItem.media_id],
            set_={"comment": comment},
        )
    )
    db.commit()
    return PublicSelectionItemResponse(selected=True, comment=comment)


@router.delete(
    "/selection/items/{media_id}",
    status_code=204,
    summary="Retirer une photo de la sélection",
)
def delete_selection_item(
    media_id: int, scope: CurrentClient, db: Session = Depends(get_db)
) -> None:
    _assert_in_scope(db, scope, media_id)
    selection = _selection(db, scope.collection_id)
    if selection is None:
        # Rien à retirer d'une sélection qui n'existe pas encore : `204`, pas `404`. Le
        # client a décoché une photo qu'il n'avait jamais cochée — l'état voulu est atteint.
        return
    _assert_selection_open(selection)
    db.execute(
        delete(SelectionItem).where(
            SelectionItem.selection_id == selection.id, SelectionItem.media_id == media_id
        )
    )
    db.commit()


@router.get(
    "/selection",
    response_model=PublicSelectionResponse,
    summary="Sélection courante",
)
def get_public_selection(
    scope: CurrentClient, db: Session = Depends(get_db)
) -> PublicSelectionResponse:
    selection = _selection(db, scope.collection_id)
    if selection is None:
        return PublicSelectionResponse(status="open", count=0, items=[])
    rows = db.execute(
        select(SelectionItem.media_id, SelectionItem.comment)
        .where(SelectionItem.selection_id == selection.id)
        .order_by(SelectionItem.media_id)
    ).all()
    return PublicSelectionResponse(
        status=cast(SelectionStatus, selection.status),
        count=len(rows),
        items=[
            PublicSelectionSummaryItem(media_id=row.media_id, comment=row.comment) for row in rows
        ],
    )


@router.post(
    "/selection/validate",
    response_model=PublicSelectionValidateResponse,
    summary="Valider la sélection — déclenche `build_delivery` et `refresh_draft_invoice`",
)
def validate_selection(
    scope: CurrentClient, db: Session = Depends(get_db)
) -> PublicSelectionValidateResponse:
    selection = _selection(db, scope.collection_id)
    count = (
        0
        if selection is None
        else int(
            db.execute(
                select(func.count())
                .select_from(SelectionItem)
                .where(SelectionItem.selection_id == selection.id)
            ).scalar_one()
        )
    )
    if selection is None or count == 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "empty_selection",
                "message": "Choisissez au moins une photo avant de valider.",
                "detail": None,
            },
        )

    existing = db.execute(
        select(Delivery).where(Delivery.selection_id == selection.id)
    ).scalar_one_or_none()
    if selection.status == "validated" and existing is not None:
        # Idempotent : revalider (double clic, retour arrière du navigateur, requête
        # rejouée) renvoie la livraison deja lancee. Creer une seconde livraison pour la
        # meme selection produirait deux archives et deux factures pour un seul achat.
        return PublicSelectionValidateResponse(
            delivery=PublicDeliveryRef(
                id=existing.id, status=cast(DeliveryReadiness, existing.status)
            )
        )

    selection.status = "validated"
    selection.validated_at = datetime.now(UTC)
    delivery = existing or Delivery(
        collection_id=scope.collection_id, selection_id=selection.id, status="pending"
    )
    db.add(delivery)
    db.flush()

    # Les deux travaux passent par la file, jamais en synchrone : la validation doit
    # repondre immediatement au client, et ni la preparation de l'archive ni la facture ne
    # doivent pouvoir la faire echouer sous ses yeux. `dedupe_key` garantit qu'un double
    # clic ne met pas deux fois le meme travail en file (§3-E.4).
    enqueue(
        db,
        "build_delivery",
        {"delivery_id": delivery.id},
        dedupe_key=f"delivery:{delivery.id}",
        priority=50,
    )
    enqueue(
        db,
        "refresh_draft_invoice",
        {"selection_id": selection.id},
        dedupe_key=f"invoice:{selection.id}",
        priority=120,
    )
    db.commit()
    return PublicSelectionValidateResponse(
        delivery=PublicDeliveryRef(id=delivery.id, status=cast(DeliveryReadiness, delivery.status))
    )


@router.get(
    "/delivery",
    response_model=PublicDeliveryStatusResponse,
    summary="État de la préparation de livraison",
)
def get_public_delivery(
    scope: CurrentClient, db: Session = Depends(get_db)
) -> PublicDeliveryStatusResponse:
    delivery = _delivery(db, scope.collection_id)
    if delivery is None:
        # Rien n'a encore ete valide : un etat d'attente, pas une absence de ressource —
        # l'ecran client affiche « en attente de votre validation », jamais une erreur.
        return PublicDeliveryStatusResponse(
            status="pending", item_count=None, byte_size=None, ready=False
        )
    return PublicDeliveryStatusResponse(
        status=cast(DeliveryReadiness, delivery.status),
        item_count=delivery.item_count,
        byte_size=delivery.byte_size,
        ready=delivery.status == "ready",
    )


@router.get(
    "/delivery/archive",
    summary="Flux ZIP — `403` si sélection non validée ou livraison non prête",
)
def get_public_delivery_archive(
    scope: CurrentClient, db: Session = Depends(get_db)
) -> StreamingResponse:
    """Le seul chemin par lequel un fichier haute definition quitte le studio.

    Le controle d'acces HD (§3-H.3) est reevalue **ici**, juste avant d'ouvrir le flux, et
    pas seulement au moment de la validation : selection validee **et** livraison prete.
    """
    selection = _selection(db, scope.collection_id)
    delivery = _delivery(db, scope.collection_id)
    if selection is None or selection.status != "validated" or delivery is None:
        raise _delivery_forbidden("Votre selection n'a pas encore ete validee.")
    if delivery.status != "ready":
        raise _delivery_forbidden("Votre livraison est encore en preparation.")

    collection = _get_collection(db, scope)
    client = db.get(Client, collection.client_id)
    filename = delivery_service.archive_filename(
        client.name if client else "client", collection.title
    )
    storage = get_storage_client()

    if delivery.storage_key is not None:
        # Grosse collection : l'archive a ete construite une fois par le worker.
        body = storage.open_stream(delivery.storage_key)
        chunks: Iterator[bytes] = body.chunks
        content_length = body.content_length
    else:
        try:
            stream = delivery_service.build_zip_stream(db, storage, selection.id)
        except delivery_service.MissingOriginalError as exc:
            # Un fichier a disparu entre la préparation et le téléchargement (purge de
            # stockage, incident). Sans ce filet, l'exception remonterait en `500` avec une
            # trace technique sous les yeux du client — ce que l'espace client s'interdit.
            # La livraison repasse en échec pour que le studio le voie, plutôt que de
            # laisser un « prêt » mensonger que le client réessaierait en boucle.
            delivery.status = "failed"
            delivery.error = str(exc)
            db.commit()
            raise _delivery_forbidden(
                "Vos fichiers ne sont plus disponibles. Le studio a été prévenu."
            ) from exc
        chunks = iter(stream)
        # `ZIP_STORED` permet d'annoncer la taille exacte avant d'avoir produit un octet :
        # le navigateur affiche une vraie progression au lieu d'un compteur qui tourne.
        content_length = len(stream)

    disposition = 'attachment; filename="' + filename + '"'
    return StreamingResponse(
        chunks,
        media_type="application/zip",
        headers={
            "Content-Length": str(content_length),
            "Content-Disposition": disposition,
        },
    )
