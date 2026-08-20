"""`media` — liste, détail, flux binaire médié (§3-H.3 : jamais d'URL présignée),
rattachement manuel, et (J2) rattachement/OCR manuels.
"""

from typing import Literal

from fastapi import APIRouter, Query, Security
from fastapi.responses import StreamingResponse

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.common import Page
from apex.schemas.media import (
    MediaAttachRequest,
    MediaEngagementAttachRequest,
    MediaEngagementOut,
    MediaOut,
    MediaSummary,
)
from apex.schemas.review import MediaOcrResponse

router = APIRouter(prefix="/media", tags=["media"], dependencies=[Security(bearer_scheme)])


@router.get("", response_model=Page[MediaSummary], summary="Liste des médias")
def list_media(
    shooting_id: int | None = None,
    status: str | None = None,
    batch_id: int | None = None,
    unattached: bool = False,
    quarantined: bool = False,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[MediaSummary]:
    not_implemented("GET /media")


@router.get("/{media_id}", response_model=MediaOut, summary="Fiche média complète")
def get_media(media_id: int) -> MediaOut:
    not_implemented("GET /media/{id}")


@router.get(
    "/{media_id}/file/{variant}",
    summary="Flux binaire médié (thumb | preview | hd) — jamais d'URL présignée vers R2",
)
def get_media_file(media_id: int, variant: Literal["thumb", "preview", "hd"]) -> StreamingResponse:
    not_implemented("GET /media/{id}/file/{variant}")


@router.post(
    "/{media_id}/attach",
    response_model=MediaOut,
    summary="Rattachement manuel depuis le bac « à rattacher »",
)
def attach_media(media_id: int, payload: MediaAttachRequest) -> MediaOut:
    not_implemented("POST /media/{id}/attach")


@router.post(
    "/{media_id}/engagements",
    response_model=MediaEngagementOut,
    status_code=201,
    summary="Rattachement manuel à un engagement (J2, `source='human'`)",
)
def add_media_engagement(
    media_id: int, payload: MediaEngagementAttachRequest
) -> MediaEngagementOut:
    not_implemented("POST /media/{id}/engagements")


@router.delete(
    "/{media_id}/engagements/{engagement_id}",
    status_code=204,
    summary="Retirer un rattachement (J2)",
)
def delete_media_engagement(media_id: int, engagement_id: int) -> None:
    not_implemented("DELETE /media/{id}/engagements/{engagement_id}")


@router.get(
    "/{media_id}/ocr",
    response_model=MediaOcrResponse,
    summary="Candidats OCR bruts du média (J2) — score et boîte, affichés dans l'UI",
)
def get_media_ocr(media_id: int) -> MediaOcrResponse:
    not_implemented("GET /media/{id}/ocr")
