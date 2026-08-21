"""`collection` (J2) + livraison/partage côté studio (J3, §3-L/§3-M).

Les routes `/public/**` (jeton client) vivent dans `routers/public.py`, un routeur dédié
et cloisonné — jamais mélangées ici (§3-L.3).

Cloisonnement (§3-I, matrice) : « Collections, liens de partage — dirigeant : oui,
photographe : lecture seule. » Pas de restriction par shooting affecté (contrairement aux
médias) — un photographe voit **toutes** les collections, il ne peut simplement pas en créer,
les composer ni les publier.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Client
from apex.models.collection import Collection, CollectionItem
from apex.models.media import Media
from apex.models.shooting import Shooting
from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.billing import (
    SelectionOut,
    ShareLinkCreateRequest,
    ShareLinkCreateResponse,
    ShareLinkOut,
)
from apex.schemas.collection import (
    CollectionAddItemsRequest,
    CollectionAddItemsResponse,
    CollectionCreate,
    CollectionItemOut,
    CollectionOut,
)
from apex.schemas.common import Page
from apex.schemas.search import FromSearchFilters
from apex.security import CurrentUser
from apex.services import access
from apex.services.facets import SearchFilters, collect_media_ids
from apex.services.pagination import paginate_by_id

router = APIRouter(
    prefix="/collections", tags=["collections"], dependencies=[Security(bearer_scheme)]
)


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "not_found", "message": f"{resource} introuvable.", "detail": None},
    )


def _collection_out(db: Session, collection: Collection) -> CollectionOut:
    items = db.execute(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection.id)
        .order_by(CollectionItem.position, CollectionItem.media_id)
    ).scalars()
    return CollectionOut(
        id=collection.id,
        client_id=collection.client_id,
        shooting_id=collection.shooting_id,
        title=collection.title,
        description=collection.description,
        status=collection.status,
        published_at=collection.published_at,
        created_by=collection.created_by,
        items=[CollectionItemOut.model_validate(i) for i in items],
    )


def _get_collection_or_404(db: Session, collection_id: int) -> Collection:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise _not_found("Collection")
    return collection


@router.get("", response_model=Page[CollectionOut], summary="Liste des collections")
def list_collections(
    user: CurrentUser,
    db: Session = Depends(get_db),
    client_id: int | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[CollectionOut]:
    stmt = select(Collection)
    if client_id is not None:
        stmt = stmt.where(Collection.client_id == client_id)
    if status is not None:
        stmt = stmt.where(Collection.status == status)
    items, next_cursor, total = paginate_by_id(
        db, stmt, Collection.id, cursor=cursor, limit=limit, with_total=True
    )
    return Page(items=[_collection_out(db, c) for c in items], next_cursor=next_cursor, total=total)


@router.post("", response_model=CollectionOut, status_code=201, summary="Créer une collection")
def create_collection(
    payload: CollectionCreate, user: CurrentUser, db: Session = Depends(get_db)
) -> CollectionOut:
    access.require_owner(user, message="Seul le dirigeant peut créer une collection.")
    if db.get(Client, payload.client_id) is None:
        raise _not_found("Client")
    if payload.shooting_id is not None and db.get(Shooting, payload.shooting_id) is None:
        raise _not_found("Shooting")

    collection = Collection(
        client_id=payload.client_id,
        shooting_id=payload.shooting_id,
        title=payload.title,
        description=payload.description,
        status="draft",
        created_by=user.id,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return _collection_out(db, collection)


@router.get("/{collection_id}", response_model=CollectionOut, summary="Détail + items paginés")
def get_collection(
    collection_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> CollectionOut:
    collection = _get_collection_or_404(db, collection_id)
    return _collection_out(db, collection)


def _filters_from_payload(payload: FromSearchFilters) -> SearchFilters:
    """`from_search` porte les **mêmes paramètres** que `GET /search` (contrat §3-K), en
    JSON plutôt qu'en query string.

    Revue J2 (🟡 12) : `payload` est désormais un `FromSearchFilters` (Pydantic) plutôt
    qu'un `dict[str, Any]` — un champ mal typé est refusé en `422` par FastAPI avant même
    d'atteindre cette fonction, jamais un `500` en aval de `services/facets.py`.
    """
    return SearchFilters(
        q=payload.q,
        shooting_id=payload.shooting_id,
        client_id=payload.client_id,
        team_id=payload.team_id,
        driver_id=payload.driver_id,
        car_number=payload.car_number,
        circuit_id=payload.circuit_id,
        camera_id=payload.camera_id,
        lens=payload.lens,
        iso_min=payload.iso_min,
        iso_max=payload.iso_max,
        focal_min=payload.focal_min,
        focal_max=payload.focal_max,
        date_from=payload.date_from,
        date_to=payload.date_to,
        status=payload.status,
        series=payload.series,
    )


@router.post(
    "/{collection_id}/items",
    response_model=CollectionAddItemsResponse,
    summary="Ajouter des médias — sélection explicite ou depuis une requête de recherche",
)
def add_collection_items(
    collection_id: int,
    payload: CollectionAddItemsRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> CollectionAddItemsResponse:
    access.require_owner(user, message="Seul le dirigeant peut composer une collection.")
    _get_collection_or_404(db, collection_id)

    if payload.media_ids is not None:
        media_ids = list(dict.fromkeys(payload.media_ids))  # dédoublonne, ordre stable
    elif payload.from_search is not None:
        filters = _filters_from_payload(payload.from_search)
        media_ids = collect_media_ids(db, user, filters)
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_request",
                "message": "« media_ids » ou « from_search » requis.",
                "detail": None,
            },
        )

    if not media_ids:
        return CollectionAddItemsResponse(added=0, skipped_duplicates=0)

    # Revue J2 (🟡 13) : `media_ids` explicite peut viser un id inexistant —
    # `on_conflict_do_nothing(index_elements=["collection_id", "media_id"])` ne couvre que
    # les doublons, pas une violation de la FK vers `media` (`500` reproduit). Filtré ici
    # plutôt que rattrapé après coup : un id inconnu est silencieusement ignoré, comme un
    # doublon — jamais une raison de faire échouer le reste du lot.
    existing_media_ids = set(db.execute(select(Media.id).where(Media.id.in_(media_ids))).scalars())
    media_ids = [mid for mid in media_ids if mid in existing_media_ids]
    if not media_ids:
        return CollectionAddItemsResponse(added=0, skipped_duplicates=0)

    next_position = (
        int(
            db.execute(
                select(CollectionItem.position)
                .where(CollectionItem.collection_id == collection_id)
                .order_by(CollectionItem.position.desc())
                .limit(1)
            ).scalar_one_or_none()
            or -1
        )
        + 1
    )

    added = 0
    for offset, media_id in enumerate(media_ids):
        result = db.execute(
            pg_insert(CollectionItem)
            .values(collection_id=collection_id, media_id=media_id, position=next_position + offset)
            .on_conflict_do_nothing(index_elements=["collection_id", "media_id"])
            .returning(CollectionItem.media_id)
        )
        if result.first() is not None:
            added += 1
    db.commit()

    return CollectionAddItemsResponse(added=added, skipped_duplicates=len(media_ids) - added)


@router.delete("/{collection_id}/items/{media_id}", status_code=204, summary="Retirer un média")
def delete_collection_item(
    collection_id: int, media_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> None:
    access.require_owner(user, message="Seul le dirigeant peut modifier une collection.")
    _get_collection_or_404(db, collection_id)
    item = db.get(CollectionItem, (collection_id, media_id))
    if item is None:
        raise _not_found("Média de la collection")
    db.delete(item)
    db.commit()


@router.post("/{collection_id}/publish", response_model=CollectionOut, summary="Publier")
def publish_collection(
    collection_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> CollectionOut:
    access.require_owner(user, message="Seul le dirigeant peut publier une collection.")
    collection = _get_collection_or_404(db, collection_id)
    if collection.status != "published":
        collection.status = "published"
        collection.published_at = datetime.now(UTC)
        db.commit()
        db.refresh(collection)
    return _collection_out(db, collection)


# --- J3 : partage et sélection côté studio (§3-L, §3-M) ---------------------------------


@router.post(
    "/{collection_id}/share-links",
    response_model=ShareLinkCreateResponse,
    status_code=201,
    summary="Créer un lien de partage — le jeton en clair n'est renvoyé qu'une fois",
)
def create_share_link(
    collection_id: int, payload: ShareLinkCreateRequest
) -> ShareLinkCreateResponse:
    not_implemented("POST /collections/{id}/share-links")


@router.get(
    "/{collection_id}/share-links",
    response_model=list[ShareLinkOut],
    summary="Liste des liens actifs — statistiques de vue",
)
def list_share_links(collection_id: int) -> list[ShareLinkOut]:
    not_implemented("GET /collections/{id}/share-links")


@router.get(
    "/{collection_id}/selection",
    response_model=SelectionOut,
    summary="Sélection client de la collection",
)
def get_collection_selection(collection_id: int) -> SelectionOut:
    not_implemented("GET /collections/{id}/selection")
