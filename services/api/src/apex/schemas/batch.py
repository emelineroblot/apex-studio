"""Schémas d'upload par lot : `upload_batch`, `pipeline_event` (vue de suivi)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

BatchStatus = Literal["open", "processing", "closed"]


class BatchCreateRequest(BaseModel):
    expected_count: int
    shooting_hint_id: int | None = None


class BatchCreateResponse(BaseModel):
    id: int
    status: BatchStatus
    expected_count: int


class BatchCloseResponse(BaseModel):
    id: int
    status: BatchStatus


class FileUploadResponse(BaseModel):
    """`duplicate=true` signifie que l'`Idempotency-Key` a déjà été vue (rejeu, §3-F.4.2)."""

    media_id: int
    status: Literal["uploaded"]
    duplicate: bool


class PipelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: str
    status: str
    duration_ms: int | None
    message: str | None
    created_at: datetime


class BatchStatusCounts(BaseModel):
    uploaded: int
    processing: int
    ingested: int
    quarantined: int


class BatchStatusResponse(BaseModel):
    """Cible d'un polling 1 s côté frontend — déclenche un tick si la file n'est pas vide."""

    id: int
    expected_count: int
    received_count: int
    counts: BatchStatusCounts
    attached_count: int
    duplicate_count: int
    progress: float
    missing_count: int
    done: bool
    events: list[PipelineEventOut]
