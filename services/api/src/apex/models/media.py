"""Ingestion : `upload_batch`, `media`, `media_series`, `media_engagement`, `pipeline_event`.

Deux axes d'état orthogonaux sur `media` (§3-F.2 du plan) : `ingest_status` (santé du
fichier) et `attachment_status` (avancement du rattachement) — jamais fusionnés dans un
seul champ. `shot_at_exif` (naïf, tel que lu) et `shot_at` (calculé, `timestamptz`) sont
deux colonnes distinctes : ne jamais les confondre (§3-F.3, fuseaux horaires).
"""

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base, IdMixin, TimestampMixin

UPLOAD_BATCH_STATUSES = ("open", "processing", "closed")
INGEST_STATUSES = ("uploaded", "processing", "ingested", "quarantined")
ATTACHMENT_STATUSES = (
    "unattached",
    "shooting_attached",
    "engagement_attached",
    "pending_review",
    "inconsistent",
)
ATTACHMENT_SOURCES = ("pipeline_time", "pipeline_ocr", "human")
MEDIA_ENGAGEMENT_SOURCES = ("ocr", "human")

# Énumération fermée des motifs de quarantaine (§3-F.2) — chaque valeur a un libellé
# français côté frontend. `orphan_object` est ajouté par `sweep_orphans` (§3-F.4.6).
QUARANTINE_REASONS = (
    "truncated_file",
    "not_an_image",
    "unsupported_mime",
    "dimensions_out_of_range",
    "aspect_ratio_out_of_range",
    "exif_inconsistent",
    "too_large",
    "quota_exceeded",
    "ingest_failed",
    "orphan_object",
)


class UploadBatch(Base):
    __tablename__ = "upload_batch"
    __table_args__ = (
        CheckConstraint(f"status IN {UPLOAD_BATCH_STATUSES}", name="status_valid"),
        Index("ix_upload_batch_created_by_started_at", "created_by", desc("started_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    shooting_hint_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shooting.id", ondelete="SET NULL")
    )
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Media(TimestampMixin, Base):
    """Une photo, du dépôt à l'état terminal. Jamais supprimée (invariant `AGENTS.md`)."""

    __tablename__ = "media"
    __table_args__ = (
        UniqueConstraint("batch_id", "idempotency_key", name="batch_idempotency"),
        CheckConstraint(
            "ingest_status <> 'quarantined' OR quarantine_reason IS NOT NULL",
            name="quarantine_reason_required",
        ),
        CheckConstraint(
            "attachment_status <> 'shooting_attached' OR shooting_id IS NOT NULL",
            name="shooting_attached_requires_shooting",
        ),
        CheckConstraint(f"ingest_status IN {INGEST_STATUSES}", name="ingest_status_valid"),
        CheckConstraint(
            f"attachment_status IN {ATTACHMENT_STATUSES}", name="attachment_status_valid"
        ),
        CheckConstraint(
            f"quarantine_reason IS NULL OR quarantine_reason IN {QUARANTINE_REASONS}",
            name="quarantine_reason_valid",
        ),
        CheckConstraint(
            f"attachment_source IS NULL OR attachment_source IN {ATTACHMENT_SOURCES}",
            name="attachment_source_valid",
        ),
        Index("ix_media_content_hash", "content_hash"),
        Index("ix_media_shooting_id_shot_at", "shooting_id", "shot_at"),
        Index("ix_media_camera_id_shot_at", "camera_id", "shot_at"),
        Index("ix_media_batch_id", "batch_id"),
        # Partiel : ne couvre que les médias pas encore terminaux (bac « à rattacher »,
        # quarantaine, en cours) — la grande majorité des lignes une fois le pipeline
        # stabilisé n'ont pas besoin d'y figurer.
        Index(
            "ix_media_ingest_status_pending",
            "ingest_status",
            postgresql_where=text("ingest_status <> 'ingested'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("upload_batch.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    mime: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    storage_key_hd: Mapped[str | None] = mapped_column(Text)
    storage_key_preview: Mapped[str | None] = mapped_column(Text)
    storage_key_thumb: Mapped[str | None] = mapped_column(Text)

    # Naïf, tel que lu dans l'EXIF (pas de fuseau) — ne jamais comparer directement à
    # `shooting.period` (tstzrange, timezone-aware). Voir `shot_at`.
    shot_at_exif: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    # Calculé : `localize(shot_at_exif, camera.timezone) + camera.clock_offset_seconds`.
    shot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("camera.id", ondelete="SET NULL")
    )
    lens_model: Mapped[str | None] = mapped_column(String(255))
    iso: Mapped[int | None] = mapped_column(Integer)
    shutter_speed_sec: Mapped[float | None] = mapped_column(Numeric(12, 6))
    shutter_speed_label: Mapped[str | None] = mapped_column(String(50))
    aperture: Mapped[float | None] = mapped_column(Numeric(6, 2))
    focal_length: Mapped[float | None] = mapped_column(Numeric(8, 2))
    gps_lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    gps_lon: Mapped[float | None] = mapped_column(Numeric(9, 6))
    exif_raw: Mapped[dict | None] = mapped_column(JSONB)

    phash: Mapped[int | None] = mapped_column(BigInteger)
    sharpness: Mapped[float | None] = mapped_column(Numeric(12, 4))
    series_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media_series.id", ondelete="SET NULL", use_alter=True)
    )
    is_series_representative: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    duplicate_of_media_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="SET NULL")
    )

    ingest_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="uploaded"
    )
    quarantine_reason: Mapped[str | None] = mapped_column(String(50))
    quarantine_detail: Mapped[dict | None] = mapped_column(JSONB)

    attachment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="unattached"
    )
    attachment_source: Mapped[str | None] = mapped_column(String(20))
    attachment_detail: Mapped[dict | None] = mapped_column(JSONB)
    shooting_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shooting.id", ondelete="SET NULL")
    )

    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    caption: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


class MediaSeries(IdMixin, Base):
    """Regroupement de rafales (§3-G.3) — le représentant est le membre le plus net."""

    __tablename__ = "media_series"
    __table_args__ = (Index("ix_media_series_shooting_id", "shooting_id"),)

    shooting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shooting.id", ondelete="CASCADE"), nullable=False
    )
    camera_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("camera.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    representative_media_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="SET NULL")
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class MediaEngagement(Base):
    """Rattachement média ↔ engagement — un média peut en avoir **plusieurs** (PK composite)."""

    __tablename__ = "media_engagement"

    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    engagement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("engagement.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(f"source IN {MEDIA_ENGAGEMENT_SOURCES}", name="source_valid"),
        Index("ix_media_engagement_engagement_id", "engagement_id"),
    )


class PipelineEvent(Base):
    """Journal d'ingestion — une ligne par étape, lisible directement dans l'UI de lot."""

    __tablename__ = "pipeline_event"
    __table_args__ = (
        Index("ix_pipeline_event_batch_id_created_at", "batch_id", "created_at"),
        Index("ix_pipeline_event_media_id_created_at", "media_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    media_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE")
    )
    batch_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("upload_batch.id", ondelete="CASCADE")
    )
    job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("job.id", ondelete="SET NULL")
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
