"""Schémas des réglages OCR (J2, §3-J.2) — Directives du principe DOE, éditables en UI."""

from datetime import datetime

from pydantic import BaseModel


class OcrDistribution(BaseModel):
    auto: int
    review: int
    abstain: int
    not_engaged: int


class OcrSettingsOut(BaseModel):
    high: float
    low: float
    min_box_area_ratio: float
    max_box_area_ratio: float
    engine_version: str
    updated_at: datetime
    distribution: OcrDistribution


class OcrSettingsUpdate(BaseModel):
    high: float
    low: float
    min_box_area_ratio: float | None = None
    max_box_area_ratio: float | None = None


class OcrPreviewDistribution(BaseModel):
    auto: int
    review: int
    abstain: int


class OcrSettingsUpdateResponse(BaseModel):
    """`reclassify_job_id` : re-projection des candidats existants — jamais de ré-inférence."""

    settings: OcrSettingsOut
    reclassify_job_id: int
    preview_distribution: OcrPreviewDistribution
