"""Référentiel métier : `client`, `circuit`, `team`, `driver`, `camera`."""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base, IdMixin, TimestampMixin

CLIENT_KINDS = ("team", "driver", "sponsor")


class Client(IdMixin, TimestampMixin, Base):
    __tablename__ = "client"
    __table_args__ = (CheckConstraint(f"kind IN {CLIENT_KINDS}", name="kind_valid"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Circuit(IdMixin, TimestampMixin, Base):
    __tablename__ = "circuit"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    city: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Europe/Paris")


class Team(IdMixin, TimestampMixin, Base):
    __tablename__ = "team"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("client.id", ondelete="SET NULL")
    )


class Driver(IdMixin, TimestampMixin, Base):
    __tablename__ = "driver"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    nationality: Mapped[str | None] = mapped_column(String(100))


class Camera(IdMixin, TimestampMixin, Base):
    __tablename__ = "camera"

    exif_serial: Mapped[str | None] = mapped_column(String(255), unique=True)
    make: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    clock_offset_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Europe/Paris")
