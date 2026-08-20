"""`media` — liste, détail, flux binaire médié (§3-H.3 : jamais d'URL présignée),
rattachement manuel, et (J2) rattachement/OCR manuels.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.media import Media, MediaEngagement, PipelineEvent
from apex.models.shooting import Engagement
from apex.routers._common import not_implemented
from apex.schemas.common import Page
from apex.schemas.media import (
    MediaAttachRequest,
    MediaEngagementAttachRequest,
    MediaEngagementOut,
    MediaExif,
    MediaOut,
    MediaSummary,
)
from apex.schemas.review import MediaOcrResponse
from apex.security import CurrentUser
from apex.services import access
from apex.services.pagination import paginate_by_id
from apex.services.storage import ObjectNotFoundError, get_storage_client

router = APIRouter(prefix="/media", tags=["media"])

VARIANT_CONTENT_TYPES = {"thumb": "image/webp", "preview": "image/webp", "hd": "image/jpeg"}
VARIANT_STORAGE_ATTR = {
    "thumb": "storage_key_thumb",
    "preview": "storage_key_preview",
    "hd": "storage_key_hd",
}


def _thumb_url(media_id: int) -> str:
    return f"/api/v1/media/{media_id}/file/thumb"


def _to_summary(media: Media) -> MediaSummary:
    return MediaSummary(
        id=media.id,
        thumb_url=_thumb_url(media.id),
        shot_at=media.shot_at,
        ingest_status=media.ingest_status,
        attachment_status=media.attachment_status,
        shooting_id=media.shooting_id,
        is_simulated=media.is_simulated,
        duplicate_of_media_id=media.duplicate_of_media_id,
    )


@router.get("", response_model=Page[MediaSummary], summary="Liste des médias")
def list_media(
    user: CurrentUser,
    db: Session = Depends(get_db),
    shooting_id: int | None = None,
    status: str | None = None,
    batch_id: int | None = None,
    unattached: bool = False,
    quarantined: bool = False,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[MediaSummary]:
    stmt = select(Media)
    visibility = access.media_visibility_clause(user)
    if visibility is not None:
        stmt = stmt.where(visibility)
    if shooting_id is not None:
        stmt = stmt.where(Media.shooting_id == shooting_id)
    if status is not None:
        stmt = stmt.where(Media.ingest_status == status)
    if batch_id is not None:
        stmt = stmt.where(Media.batch_id == batch_id)
    if unattached:
        stmt = stmt.where(Media.attachment_status == "unattached")
    if quarantined:
        stmt = stmt.where(Media.ingest_status == "quarantined")

    items, next_cursor = paginate_by_id(db, stmt, Media.id, cursor=cursor, limit=limit)
    return Page(items=[_to_summary(m) for m in items], next_cursor=next_cursor)


def _media_out(db: Session, media: Media) -> MediaOut:
    engagement_rows = db.execute(
        select(MediaEngagement, Engagement.car_number)
        .join(Engagement, Engagement.id == MediaEngagement.engagement_id)
        .where(MediaEngagement.media_id == media.id)
    ).all()
    engagements = [
        MediaEngagementOut(
            engagement_id=me.engagement_id,
            car_number=car_number,
            source=me.source,
            confidence=float(me.confidence) if me.confidence is not None else None,
        )
        for me, car_number in engagement_rows
    ]

    event_rows = (
        db.execute(
            select(PipelineEvent)
            .where(PipelineEvent.media_id == media.id)
            .order_by(PipelineEvent.created_at)
        )
        .scalars()
        .all()
    )
    events = [
        f"{e.step}: {e.status}" + (f" — {e.message}" if e.message else "") for e in event_rows
    ]

    return MediaOut(
        id=media.id,
        batch_id=media.batch_id,
        original_filename=media.original_filename,
        byte_size=media.byte_size,
        mime=media.mime,
        width=media.width,
        height=media.height,
        shot_at_exif=media.shot_at_exif,
        shot_at=media.shot_at,
        exif=MediaExif(
            camera_id=media.camera_id,
            lens_model=media.lens_model,
            iso=media.iso,
            shutter_speed_sec=float(media.shutter_speed_sec)
            if media.shutter_speed_sec is not None
            else None,
            shutter_speed_label=media.shutter_speed_label,
            aperture=float(media.aperture) if media.aperture is not None else None,
            focal_length=float(media.focal_length) if media.focal_length is not None else None,
            gps_lat=float(media.gps_lat) if media.gps_lat is not None else None,
            gps_lon=float(media.gps_lon) if media.gps_lon is not None else None,
            exif_raw=media.exif_raw,
        ),
        phash=media.phash,
        sharpness=float(media.sharpness) if media.sharpness is not None else None,
        series_id=media.series_id,
        is_series_representative=media.is_series_representative,
        duplicate_of_media_id=media.duplicate_of_media_id,
        ingest_status=media.ingest_status,
        quarantine_reason=media.quarantine_reason,
        quarantine_detail=media.quarantine_detail,
        attachment_status=media.attachment_status,
        attachment_source=media.attachment_source,
        attachment_detail=media.attachment_detail,
        shooting_id=media.shooting_id,
        is_simulated=media.is_simulated,
        caption=media.caption,
        keywords=media.keywords,
        engagements=engagements,
        events=events,
    )


@router.get("/{media_id}", response_model=MediaOut, summary="Fiche média complète")
def get_media(media_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> MediaOut:
    media = access.get_visible_media_or_404(db, user, media_id)
    return _media_out(db, media)


@router.get(
    "/{media_id}/file/{variant}",
    summary="Flux binaire médié (thumb | preview | hd) — jamais d'URL présignée vers R2",
)
def get_media_file(
    media_id: int,
    variant: Literal["thumb", "preview", "hd"],
    user: CurrentUser,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    media = access.get_visible_media_or_404(db, user, media_id)

    # §3-H.3, point 3 : le HD n'est jamais servi avant validation. En J1, seuls des rôles
    # internes existent (pas encore d'espace client, J3) — donc toujours autorisé ici, la
    # restriction s'active dès que la portée « client » sera câblée.
    storage_key = getattr(media, VARIANT_STORAGE_ATTR[variant])
    if storage_key is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "variant_not_ready",
                "message": "Cette variante n'est pas encore disponible.",
                "detail": None,
            },
        )

    etag = f'"{media.content_hash.hex()}"' if media.content_hash else f'"media-{media.id}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    storage = get_storage_client()
    try:
        body = storage.open_stream(storage_key)
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "object_missing", "message": "Fichier introuvable.", "detail": None},
        ) from exc

    headers = {
        "ETag": etag,
        "Cache-Control": "private, max-age=3600",
        "Content-Length": str(body.content_length),
    }
    return StreamingResponse(
        body.chunks,
        media_type=VARIANT_CONTENT_TYPES[variant],
        headers=headers,
    )


@router.post(
    "/{media_id}/attach",
    response_model=MediaOut,
    summary="Rattachement manuel depuis le bac « à rattacher »",
)
def attach_media(
    media_id: int, payload: MediaAttachRequest, user: CurrentUser, db: Session = Depends(get_db)
) -> MediaOut:
    media = access.get_visible_media_or_404(db, user, media_id)
    shooting = access.get_visible_shooting_or_404(db, user, payload.shooting_id)

    media.shooting_id = shooting.id
    media.attachment_status = "shooting_attached"
    media.attachment_source = "human"
    media.attachment_detail = None
    db.commit()
    db.refresh(media)
    return _media_out(db, media)


@router.post(
    "/{media_id}/engagements",
    response_model=MediaEngagementOut,
    status_code=201,
    summary="Rattachement manuel à un engagement (J2, `source='human'`)",
)
def add_media_engagement(
    media_id: int, payload: MediaEngagementAttachRequest, user: CurrentUser
) -> MediaEngagementOut:
    not_implemented("POST /media/{id}/engagements")


@router.delete(
    "/{media_id}/engagements/{engagement_id}",
    status_code=204,
    summary="Retirer un rattachement (J2)",
)
def delete_media_engagement(media_id: int, engagement_id: int, user: CurrentUser) -> None:
    not_implemented("DELETE /media/{id}/engagements/{engagement_id}")


@router.get(
    "/{media_id}/ocr",
    response_model=MediaOcrResponse,
    summary="Candidats OCR bruts du média (J2) — score et boîte, affichés dans l'UI",
)
def get_media_ocr(media_id: int, user: CurrentUser) -> MediaOcrResponse:
    not_implemented("GET /media/{id}/ocr")
