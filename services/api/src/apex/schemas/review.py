"""Schémas de la file de validation OCR (J2, §3-J.4).

`OcrResolution` et `OcrBoundingBox` ferment deux trous de contrat relevés à l'ouverture du
lot recherche/collections (le frontend les avait contournés par déduction, cf.
`.agent-team/implementation.md`) :

- **`OcrResolution`** — doit rester égal, valeur pour valeur, à
  `apex.models.search.OCR_RESOLUTIONS` (`CHECK resolution_valid` en base). Même mécanisme
  que `QuarantineReason` (`apex.schemas.media`, § pièges projet : « un dictionnaire
  incomplet doit être une erreur de compilation ») — verrouillé par
  `tests/test_openapi_contract.py::test_ocr_resolution_enum_matches_model`. Exposé
  explicitement sur `ReviewItem` **et** `OcrCandidateOut` : la distinction entre « pas sûr »
  (`review`, score entre les seuils) et « sûr mais incohérent » (`not_engaged`, numéro
  absent des engagements) ne doit plus se déduire de la nullabilité de
  `suggested_engagement` — un candidat `review` a *toujours* un engagement suggéré (c'est
  la condition même de la bande de seuils, §3-J.3), donc cette déduction n'aurait jamais
  distingué les deux cas si `GET /review/queue` en venait à exposer un jour les deux
  ensemble (ex. tri par shooting mêlant plusieurs résolutions).
- **`OcrBoundingBox`** — remplace le `dict[str, Any]` non contraint. Convention posée par
  `apex.pipeline.ocr.scoring.bbox_payload` (source de vérité) : `x/y/w/h` sont la boîte
  englobante du quadrilatère détecté, **normalisée** en fraction de l'image `[0, 1]`
  (indépendante de la résolution d'affichage) ; `quad` est le quadrilatère brut, en
  **pixels** de l'image analysée (l'aperçu 1600 px), conservé pour un rendu incliné ou du
  débogage ; `image_width`/`image_height` donnent l'échelle du quadrilatère.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

# Doit rester égal, valeur pour valeur, à `apex.models.search.OCR_RESOLUTIONS` (CHECK en
# base). Voir docstring de module — verrouillé par `tests/test_openapi_contract.py`.
OcrResolution = Literal["auto", "review", "abstain", "not_engaged", "accepted", "rejected"]

ReviewAction = Literal["accept", "reject", "reassign"]


class OcrBoundingBox(BaseModel):
    """Boîte de détection — voir docstring de module pour la convention `x/y/w/h`/`quad`."""

    model_config = ConfigDict(extra="ignore")

    x: float
    y: float
    w: float
    h: float
    quad: list[list[float]] | None = None
    image_width: int | None = None
    image_height: int | None = None


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
    bbox: OcrBoundingBox
    # Toujours `"review"` tant que `GET /review/queue` ne filtre que la bande de seuils
    # (§3-J.3) — exposé explicitement plutôt que déduit, voir docstring de module.
    resolution: OcrResolution
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
    bbox: OcrBoundingBox
    engine_version: str
    resolution: OcrResolution
    engagement_id: int | None


class MediaOcrResponse(BaseModel):
    candidates: list[OcrCandidateOut]
