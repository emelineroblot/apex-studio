"""`/settings/ocr` — Directives du principe DOE (§3-J.2) : seuils éditables, jamais en dur.

Écriture réservée à `owner` (contrat J2) — appliqué au Lot 1 via `require_role`.
"""

from fastapi import APIRouter, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.settings import OcrSettingsOut, OcrSettingsUpdate, OcrSettingsUpdateResponse

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Security(bearer_scheme)])


@router.get("/ocr", response_model=OcrSettingsOut, summary="Seuils OCR courants")
def get_ocr_settings() -> OcrSettingsOut:
    not_implemented("GET /settings/ocr")


@router.put(
    "/ocr",
    response_model=OcrSettingsUpdateResponse,
    summary="Modifier les seuils OCR — `owner` uniquement, simule la redistribution",
)
def put_ocr_settings(payload: OcrSettingsUpdate) -> OcrSettingsUpdateResponse:
    not_implemented("PUT /settings/ocr")
