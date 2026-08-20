"""Schémas `collection`, `collection_item` (J2)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

CollectionStatus = Literal["draft", "published", "closed"]


class CollectionCreate(BaseModel):
    client_id: int
    shooting_id: int | None = None
    title: str
    description: str | None = None


class CollectionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    media_id: int
    position: int


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    shooting_id: int | None
    title: str
    description: str | None
    status: CollectionStatus
    published_at: datetime | None
    created_by: int
    items: list[CollectionItemOut] = []


class CollectionAddItemsRequest(BaseModel):
    """Composition depuis une sélection explicite **ou** depuis une requête de recherche."""

    media_ids: list[int] | None = None
    from_search: dict[str, Any] | None = None


class CollectionAddItemsResponse(BaseModel):
    added: int
    skipped_duplicates: int
