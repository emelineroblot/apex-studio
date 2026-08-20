"""Schémas de l'espace client (préfixe `/public`, jeton de partage — §3-L du plan).

Aucun identifiant de collection, de client ou de shooting n'apparaît jamais en paramètre :
la collection est celle du jeton, point (§3-L.3). Seuls des `media_id` sont acceptés,
systématiquement validés contre le périmètre du jeton.
"""

from typing import Literal

from pydantic import BaseModel

DeliveryReadiness = Literal["pending", "building", "ready", "failed"]


class PublicSessionRequest(BaseModel):
    token: str


class PublicCollectionRef(BaseModel):
    title: str
    description: str | None
    item_count: int
    studio_name: str


class PublicSessionResponse(BaseModel):
    access_token: str
    expires_in: int
    collection: PublicCollectionRef


class LinkExpiredError(BaseModel):
    code: Literal["link_expired"] = "link_expired"


class PublicMediaItem(BaseModel):
    media_id: int
    preview_url: str
    thumb_url: str
    shot_at: str | None
    car_numbers: list[str]
    selected: bool
    comment: str | None


class PublicCollectionResponse(BaseModel):
    collection: PublicCollectionRef
    items: list[PublicMediaItem]
    next_cursor: str | None


class PublicSelectionItemUpdate(BaseModel):
    comment: str | None = None


class PublicSelectionItemResponse(BaseModel):
    selected: Literal[True] = True
    comment: str | None = None


class PublicSelectionSummaryItem(BaseModel):
    media_id: int
    comment: str | None


class PublicSelectionResponse(BaseModel):
    status: Literal["open", "validated"]
    count: int
    items: list[PublicSelectionSummaryItem]


class PublicDeliveryRef(BaseModel):
    id: int
    status: DeliveryReadiness


class PublicSelectionValidateResponse(BaseModel):
    """Déclenche `build_delivery` **et** `refresh_draft_invoice` (§3-M, §3-O)."""

    status: Literal["validated"] = "validated"
    delivery: PublicDeliveryRef


class PublicDeliveryStatusResponse(BaseModel):
    status: DeliveryReadiness
    item_count: int | None
    byte_size: int | None
    ready: bool
