"""Livraison et facturation (J3) : `share_link`, `client_selection`, `selection_item`,
`delivery`, `quote`, `invoice`, `invoice_line`.

Invariant `AGENTS.md` : une facture émise est immuable. Garanti par un trigger PL/pgSQL
(§3-O du plan, migration `0001_schema_initial`), pas seulement par le code applicatif —
c'est l'invariant métier le plus fort du projet.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base, IdMixin, TimestampMixin

SELECTION_STATUSES = ("open", "validated")
DELIVERY_STATUSES = ("pending", "building", "ready", "failed")
QUOTE_STATUSES = ("draft", "sent", "accepted", "refused")
INVOICE_STATUSES = ("draft", "issued")


class ShareLink(Base):
    """Jeton opaque — jamais stocké en clair, seul `token_hash` (sha256) l'est (§3-L.1)."""

    __tablename__ = "share_link"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    collection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ClientSelection(IdMixin, TimestampMixin, Base):
    __tablename__ = "client_selection"
    __table_args__ = (CheckConstraint(f"status IN {SELECTION_STATUSES}", name="status_valid"),)

    collection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("collection.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SelectionItem(Base):
    __tablename__ = "selection_item"

    selection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client_selection.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    comment: Mapped[str | None] = mapped_column(Text)


class Delivery(IdMixin, TimestampMixin, Base):
    __tablename__ = "delivery"
    __table_args__ = (
        CheckConstraint(f"status IN {DELIVERY_STATUSES}", name="status_valid"),
        Index("ix_delivery_selection_id", "selection_id"),
    )

    collection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    selection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client_selection.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    storage_key: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    item_count: Mapped[int | None] = mapped_column(Integer)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Quote(IdMixin, TimestampMixin, Base):
    __tablename__ = "quote"
    __table_args__ = (CheckConstraint(f"status IN {QUOTE_STATUSES}", name="status_valid"),)

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client.id", ondelete="RESTRICT"), nullable=False
    )
    circuit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("circuit.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_shooting_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shooting.id", ondelete="SET NULL")
    )


class Invoice(IdMixin, TimestampMixin, Base):
    """Immuabilité garantie par trigger PL/pgSQL (§3-O) — pas seulement par ce `CHECK`."""

    __tablename__ = "invoice"
    __table_args__ = (
        CheckConstraint(f"status IN {INVOICE_STATUSES}", name="status_valid"),
        CheckConstraint(
            "status <> 'issued' OR (number IS NOT NULL AND issued_at IS NOT NULL)",
            name="issued_requires_number_and_date",
        ),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client.id", ondelete="RESTRICT"), nullable=False
    )
    collection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("collection.id", ondelete="RESTRICT"), nullable=False
    )
    selection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client_selection.id", ondelete="RESTRICT"), nullable=False
    )
    number: Mapped[str | None] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.20")
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class InvoiceLine(IdMixin, Base):
    """Snapshot — aucune FK vivante vers `media` (§3-O, Décision Option 2)."""

    __tablename__ = "invoice_line"

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
