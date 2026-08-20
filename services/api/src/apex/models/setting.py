"""Réglages applicatifs — table clé/valeur `app_setting`.

Porte notamment `app_name`, `studio_name` (§6 du plan) et les seuils OCR de J2
(`ocr_high`, `ocr_low`, …) : jamais codés en dur, toujours éditables ici.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
