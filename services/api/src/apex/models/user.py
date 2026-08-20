"""Compte interne (dirigeant / photographe) — table `app_user`."""

from sqlalchemy import Boolean, CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base, IdMixin, TimestampMixin

ROLES = ("owner", "photographer")


class AppUser(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="role_valid"),)

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
