"""Le cœur métier : `shooting`, `shooting_staff`, `engagement`.

`Shooting.period` est une colonne générée `tstzrange` — indexée en GiST dans la
migration (§3-F.3 du plan). C'est elle, et non un choix manuel, qui rattache un média
à un shooting.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base, IdMixin, TimestampMixin

SHOOTING_STATUSES = ("planned", "done")

# Quota par défaut : 2 Go, aligné sur `DEFAULT_SHOOTING_QUOTA_BYTES` (.env.example).
DEFAULT_QUOTA_BYTES = 2_147_483_648


class Shooting(IdMixin, TimestampMixin, Base):
    __tablename__ = "shooting"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_starts"),
        CheckConstraint(f"status IN {SHOOTING_STATUSES}", name="status_valid"),
        # Colonne générée `period` — indexée en GiST : c'est elle qui sert au
        # rattachement temporel (`period @> media.shot_at`), §3-F.3 du plan.
        Index("ix_shooting_period_gist", "period", postgresql_using="gist"),
        Index("ix_shooting_starts_at", desc("starts_at")),
    )

    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("client.id", ondelete="SET NULL")
    )
    circuit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("circuit.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Colonne générée — persistée, indexée en GiST dans la migration (autogenerate
    # ne sait pas la produire).
    period = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="planned")
    quota_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=str(DEFAULT_QUOTA_BYTES)
    )
    notes: Mapped[str | None] = mapped_column(Text)


class ShootingStaff(Base):
    """Cloisonnement photographe : un photographe ne voit que ses shootings affectés."""

    __tablename__ = "shooting_staff"

    shooting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shooting.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)


class Engagement(IdMixin, TimestampMixin, Base):
    """Clé métier du projet : numéro de voiture → pilote → écurie → client, *pour un shooting*."""

    __tablename__ = "engagement"
    __table_args__ = (
        UniqueConstraint("shooting_id", "car_number", name="shooting_car_number"),
        Index("ix_engagement_client_id", "client_id"),
    )

    shooting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shooting.id", ondelete="CASCADE"), nullable=False
    )
    car_number: Mapped[str] = mapped_column(String(10), nullable=False)
    driver_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("driver.id", ondelete="SET NULL")
    )
    team_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("team.id", ondelete="SET NULL")
    )
    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("client.id", ondelete="SET NULL")
    )
    car_model: Mapped[str | None] = mapped_column(String(255))
