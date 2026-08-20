"""Base déclarative SQLAlchemy 2.0 partagée par tous les modèles Apex.

Convention de nommage des contraintes : nécessaire pour qu'Alembic produise des noms
stables et prévisibles, même si la révision initiale est écrite à la main plutôt
qu'autogénérée.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Classe déclarative racine — toute la métadonnée du schéma des 3 jalons."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    """PK `BIGINT GENERATED ALWAYS AS IDENTITY`, convention par défaut du projet."""

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class TimestampMixin:
    """`created_at` / `updated_at` en `TIMESTAMPTZ`, valeur serveur `now()`."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
