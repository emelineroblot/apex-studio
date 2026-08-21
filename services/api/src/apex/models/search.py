"""Intelligence J2 : `media_ocr_candidate` (candidats bruts OCR), `media_search` (projection
de recherche à facettes, 1:1 avec `media`, reconstruite par le pipeline — §3-K du plan).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    desc,
    text,
)

# `postgresql.ARRAY`, pas `sqlalchemy.ARRAY` générique (§3-K.2) : seul le comparateur
# spécifique au dialecte expose `.overlap()` (opérateur `&&`), utilisé par
# `services/facets.py` pour les facettes multi-sélection sur tableau (équipes, pilotes,
# numéros). Le générique ne le porte pas — vérifié, `hasattr(..., "overlap") is False`.
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base, IdMixin

OCR_RESOLUTIONS = ("auto", "review", "abstain", "not_engaged", "accepted", "rejected")


class MediaOcrCandidate(IdMixin, Base):
    __tablename__ = "media_ocr_candidate"
    __table_args__ = (
        CheckConstraint(f"resolution IN {OCR_RESOLUTIONS}", name="resolution_valid"),
        Index("ix_media_ocr_candidate_media_id", "media_id"),
        Index(
            "ix_media_ocr_candidate_review",
            "resolution",
            postgresql_where=text("resolution = 'review'"),
        ),
    )

    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_number: Mapped[str | None] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    bbox: Mapped[dict] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)
    engagement_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("engagement.id", ondelete="SET NULL")
    )
    resolved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaSearch(Base):
    """Projection dénormalisée — jamais lue par jointure directe (§3-K.1).

    13 index (§3-K.3 du plan) : ordre/pagination keyset, filtres scalaires, GIN sur les
    tableaux et le `tsvector`, index partiel pour la vue « rafales groupées ».
    """

    __tablename__ = "media_search"
    __table_args__ = (
        Index("ms_order_idx", desc("shot_at"), desc("media_id")),
        Index("ms_shooting_idx", "shooting_id", desc("shot_at")),
        Index("ms_client_idx", "client_id"),
        Index("ms_circuit_idx", "circuit_id"),
        Index("ms_uploaded_by_idx", "uploaded_by"),
        Index("ms_camera_idx", "camera_id"),
        Index("ms_lens_idx", "lens_model"),
        Index("ms_status_idx", "attachment_status"),
        Index("ms_iso_idx", "iso"),
        Index("ms_focal_idx", "focal_length"),
        Index("ms_teams_gin", "team_ids", postgresql_using="gin"),
        Index("ms_drivers_gin", "driver_ids", postgresql_using="gin"),
        Index("ms_numbers_gin", "car_numbers", postgresql_using="gin"),
        Index("ms_fts_gin", "search_vector", postgresql_using="gin"),
        Index(
            "ms_repr_idx",
            desc("shot_at"),
            postgresql_where=text("is_series_representative"),
        ),
    )

    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    shooting_id: Mapped[int | None] = mapped_column(BigInteger)
    # Dupliqué depuis `media.uploaded_by` — nécessaire pour reproduire, sans jointure,
    # `services/access.py::media_visibility_clause` (un photographe garde ses propres
    # dépôts visibles même avant tout rattachement à un shooting).
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger)
    client_id: Mapped[int | None] = mapped_column(BigInteger)
    # Facette « circuit » (§3-K du plan) — 1:1 via `shooting.circuit_id`, donc scalaire comme
    # `client_id`/`camera_id`, pas un tableau (contrairement à `team_ids`/`driver_ids`, qui
    # viennent de la relation N:N `media_engagement`).
    circuit_id: Mapped[int | None] = mapped_column(BigInteger)
    camera_id: Mapped[int | None] = mapped_column(BigInteger)
    lens_model: Mapped[str | None] = mapped_column(String(255))
    attachment_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # Dupliqués depuis `media` (§3-K.1, « zéro jointure côté lecture ») : nécessaires à
    # `MediaSummary` (contrat `GET /search`) sans repasser par `media` pour chaque page.
    ingest_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="uploaded"
    )
    is_simulated: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    series_id: Mapped[int | None] = mapped_column(BigInteger)
    shot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    iso: Mapped[int | None] = mapped_column(Integer)
    focal_length: Mapped[float | None] = mapped_column(Numeric(8, 2))
    team_ids: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    driver_ids: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    car_numbers: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    is_series_representative: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    duplicate_of_media_id: Mapped[int | None] = mapped_column(BigInteger)
    search_vector = mapped_column(TSVECTOR)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
