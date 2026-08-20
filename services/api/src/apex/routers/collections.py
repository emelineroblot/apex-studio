"""`collection` (J2) + livraison/partage côté studio (J3, §3-L/§3-M).

Les routes `/public/**` (jeton client) vivent dans `routers/public.py`, un routeur dédié
et cloisonné — jamais mélangées ici (§3-L.3).
"""

from fastapi import APIRouter, Query, Security

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
    CollectionOut,
)
from apex.schemas.common import Page

router = APIRouter(
    prefix="/collections", tags=["collections"], dependencies=[Security(bearer_scheme)]
)


@router.get("", response_model=Page[CollectionOut], summary="Liste des collections")
def list_collections(
    cursor: str | None = None, limit: int = Query(default=50, le=100)
) -> Page[CollectionOut]:
    not_implemented("GET /collections")


@router.post("", response_model=CollectionOut, status_code=201, summary="Créer une collection")
def create_collection(payload: CollectionCreate) -> CollectionOut:
    not_implemented("POST /collections")


@router.get("/{collection_id}", response_model=CollectionOut, summary="Détail + items paginés")
def get_collection(collection_id: int) -> CollectionOut:
    not_implemented("GET /collections/{id}")


@router.post(
    "/{collection_id}/items",
    response_model=CollectionAddItemsResponse,
    summary="Ajouter des médias — sélection explicite ou depuis une requête de recherche",
)
def add_collection_items(
    collection_id: int, payload: CollectionAddItemsRequest
) -> CollectionAddItemsResponse:
    not_implemented("POST /collections/{id}/items")


@router.delete("/{collection_id}/items/{media_id}", status_code=204, summary="Retirer un média")
def delete_collection_item(collection_id: int, media_id: int) -> None:
    not_implemented("DELETE /collections/{id}/items/{media_id}")


@router.post("/{collection_id}/publish", response_model=CollectionOut, summary="Publier")
def publish_collection(collection_id: int) -> CollectionOut:
    not_implemented("POST /collections/{id}/publish")


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
