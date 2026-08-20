"""Schémas de la file de validation OCR (J2, §3-J.4)."""

from typing import Any, Literal

from pydantic import BaseModel

ReviewAction = Literal["accept", "reject", "reassign"]


class ReviewMediaRef(BaseModel):
    id: int
    thumb_url: str
    preview_url: str
    shot_at: str | None


class SuggestedEngagement(BaseModel):
    id: int
    car_number: str
    driver: str | None
    team: str | None
    client: str | None


class ReviewItem(BaseModel):
    candidate_id: int
    media: ReviewMediaRef
    raw_text: str
    normalized_number: str | None
    confidence: float
    bbox: dict[str, Any]
    suggested_engagement: SuggestedEngagement | None
    other_engagements: list[SuggestedEngagement]


class ReviewQueueResponse(BaseModel):
    items: list[ReviewItem]
    remaining: int
    next_cursor: str | None


class ReviewDecision(BaseModel):
    candidate_id: int
    action: ReviewAction
    engagement_id: int | None = None


class ReviewDecisionsRequest(BaseModel):
    decisions: list[ReviewDecision]


class ReviewDecisionError(BaseModel):
    candidate_id: int
    message: str


class ReviewDecisionsResponse(BaseModel):
    """Traitement en lot, transaction unique ; erreurs rapportées ligne par ligne."""

    applied: int
    skipped: int
    errors: list[ReviewDecisionError]
    remaining: int


class OcrCandidateOut(BaseModel):
    """Candidat brut persisté — score et boîte, affichés dans l'UI (`GET /media/{id}/ocr`)."""

    id: int
    raw_text: str
    normalized_number: str | None
    confidence: float
    bbox: dict[str, Any]
    engine_version: str
    resolution: Literal["auto", "review", "abstain", "not_engaged", "accepted", "rejected"]
    engagement_id: int | None


class MediaOcrResponse(BaseModel):
    candidates: list[OcrCandidateOut]
