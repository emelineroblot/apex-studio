"""Schémas J3 : liens de partage, sélection, facture, devis, livraison.

Immuabilité de la facture émise (§3-O) : `InvoicePatchRequest` n'est acceptée que sur une
facture `draft` — sinon `409 invoice_issued`, et le trigger PL/pgSQL est le filet final.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SelectionStatus = Literal["open", "validated"]
InvoiceStatus = Literal["draft", "issued"]
QuoteStatus = Literal["draft", "sent", "accepted", "refused"]
DeliveryStatus = Literal["pending", "building", "ready", "failed"]


class ShareLinkCreateRequest(BaseModel):
    expires_in_days: int = 14


class ShareLinkCreateResponse(BaseModel):
    """Le `token` en clair n'est renvoyé **qu'une seule fois**, à la création (§3-L.1)."""

    id: uuid.UUID
    url: str
    token: str
    expires_at: datetime


class ShareLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url_masked: str
    expires_at: datetime
    revoked_at: datetime | None
    view_count: int
    last_seen_at: datetime | None


class SelectionItemOut(BaseModel):
    media_id: int
    comment: str | None


class SelectionOut(BaseModel):
    status: SelectionStatus
    validated_at: datetime | None
    items: list[SelectionItemOut]
    count: int


class InvoiceLineIn(BaseModel):
    label: str
    quantity: float
    unit_price_cents: int
    position: int = 0


class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    quantity: float
    unit_price_cents: int
    amount_cents: int
    position: int


class InvoiceFromSelectionRequest(BaseModel):
    vat_rate: float | None = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    collection_id: int
    selection_id: int
    number: str | None
    status: InvoiceStatus
    issued_at: datetime | None
    subtotal_cents: int
    vat_rate: float
    total_cents: int
    lines: list[InvoiceLineOut] = []


class InvoicePatchRequest(BaseModel):
    """Refusé (`409 invoice_issued`) si la facture n'est plus `draft`."""

    lines: list[InvoiceLineIn] | None = None
    vat_rate: float | None = None


class QuoteCreateRequest(BaseModel):
    client_id: int
    circuit_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    amount_cents: int


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    circuit_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    amount_cents: int
    status: QuoteStatus
    accepted_at: datetime | None
    created_shooting_id: int | None


class CreatedShootingRef(BaseModel):
    id: int
    title: str


class QuoteAcceptResponse(BaseModel):
    """L'acceptation d'un devis **crée le shooting** dans la même transaction (§3-O)."""

    quote: QuoteOut
    created_shooting: CreatedShootingRef


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: DeliveryStatus
    item_count: int | None
    byte_size: int | None
    built_at: datetime | None
    error: str | None


class DemoResetResponse(BaseModel):
    job_id: int


class CronResponse(BaseModel):
    job_id: int
