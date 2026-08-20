"""Collections (J2/J3) : `collection`, `collection_item`."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base, IdMixin, TimestampMixin

COLLECTION_STATUSES = ("draft", "published", "closed")


class Collection(IdMixin, TimestampMixin, Base):
    __tablename__ = "collection"
    __table_args__ = (
        CheckConstraint(f"status IN {COLLECTION_STATUSES}", name="status_valid"),
        Index("ix_collection_client_id_status", "client_id", "status"),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client.id", ondelete="RESTRICT"), nullable=False
    )
    shooting_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shooting.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )


class CollectionItem(Base):
    __tablename__ = "collection_item"

    collection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("collection.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
