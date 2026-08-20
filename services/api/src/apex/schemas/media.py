"""Schémas `media` — deux axes d'état orthogonaux (§3-F.2) : ne jamais les fusionner."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

IngestStatus = Literal["uploaded", "processing", "ingested", "quarantined"]
AttachmentStatus = Literal[
    "unattached", "shooting_attached", "engagement_attached", "pending_review", "inconsistent"
]
AttachmentSource = Literal["pipeline_time", "pipeline_ocr", "human"]
MediaVariant = Literal["thumb", "preview", "hd"]


class MediaSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thumb_url: str
    shot_at: datetime | None
    ingest_status: IngestStatus
    attachment_status: AttachmentStatus
    shooting_id: int | None
    is_simulated: bool
    duplicate_of_media_id: int | None


class MediaEngagementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    engagement_id: int
    car_number: str
    source: Literal["ocr", "human"]
    confidence: float | None


class MediaExif(BaseModel):
    camera_id: int | None
    lens_model: str | None
    iso: int | None
    shutter_speed_sec: float | None
    shutter_speed_label: str | None
    aperture: float | None
    focal_length: float | None
    gps_lat: float | None
    gps_lon: float | None
    exif_raw: dict[str, Any] | None


class MediaOut(BaseModel):
    """Fiche média complète : EXIF, série, doublon, engagements, journal d'événements."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    original_filename: str
    byte_size: int
    mime: str | None
    width: int | None
    height: int | None
    shot_at_exif: datetime | None
    shot_at: datetime | None
    exif: MediaExif
    phash: int | None
    sharpness: float | None
    series_id: int | None
    is_series_representative: bool
    duplicate_of_media_id: int | None
    ingest_status: IngestStatus
    quarantine_reason: str | None
    quarantine_detail: dict[str, Any] | None
    attachment_status: AttachmentStatus
    attachment_source: AttachmentSource | None
    attachment_detail: dict[str, Any] | None
    shooting_id: int | None
    is_simulated: bool
    caption: str | None
    keywords: list[str] | None
    engagements: list[MediaEngagementOut]
    events: list[str]


class MediaAttachRequest(BaseModel):
    shooting_id: int


class MediaEngagementAttachRequest(BaseModel):
    """Corps de `POST /media/{id}/engagements` (J2, rattachement manuel `source='human'`)."""

    engagement_id: int
