"""`media` — liste, détail, flux binaire médié (§3-H.3 : jamais d'URL présignée),
rattachement manuel, et (J2) rattachement/OCR manuels.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.media import Media, MediaEngagement, MediaSeries, PipelineEvent
from apex.models.search import MediaOcrCandidate
from apex.models.shooting import Engagement
from apex.pipeline.ocr import classify
from apex.schemas.common import Page
from apex.schemas.media import (
    AttachmentDetail,
    MediaAttachRequest,
    MediaEngagementAttachRequest,
    MediaEngagementOut,
    MediaExif,
    MediaOut,
    MediaSummary,
    QuarantineDetail,
)
from apex.schemas.review import MediaOcrResponse, OcrBoundingBox, OcrCandidateOut
from apex.security import CurrentUser
from apex.services import access
from apex.services.ocr_settings import load_ocr_settings
from apex.services.pagination import paginate_by_id
from apex.services.search_projection import project_media
from apex.services.storage import ObjectNotFoundError, get_storage_client

router = APIRouter(prefix="/media", tags=["media"])

VARIANT_CONTENT_TYPES = {"thumb": "image/webp", "preview": "image/webp", "hd": "image/jpeg"}
VARIANT_STORAGE_ATTR = {
    "thumb": "storage_key_thumb",
    "preview": "storage_key_preview",
    "hd": "storage_key_hd",
}


def _attachment_detail(media: Media) -> AttachmentDetail | None:
    if media.attachment_detail is None:
        return None
    return AttachmentDetail.model_validate(media.attachment_detail)


def _quarantine_detail(media: Media) -> QuarantineDetail | None:
    if media.quarantine_detail is None:
        return None
    return QuarantineDetail.model_validate(media.quarantine_detail)


def _thumb_url(media_id: int) -> str:
    # Revue J1 (bloquant n°7) : le préfixe `/api/v1` est déjà ajouté par le client HTTP du
    # frontend (`buildUrl`, cf. `AuthImage`/`apiFetchBlob`) — le laisser ici double le
    # préfixe en mode `live` (`/api/v1/api/v1/media/...`, 404 sur 100 % des vignettes).
    # Normalisé côté backend : c'est ici qu'on tranche, le frontend ne compense pas.
    return f"/media/{media_id}/file/thumb"


def _to_summary(media: Media, *, series_member_count: int | None) -> MediaSummary:
    return MediaSummary(
        id=media.id,
        thumb_url=_thumb_url(media.id),
        shot_at=media.shot_at,
        ingest_status=media.ingest_status,
        attachment_status=media.attachment_status,
        shooting_id=media.shooting_id,
        is_simulated=media.is_simulated,
        duplicate_of_media_id=media.duplicate_of_media_id,
        series_id=media.series_id,
        series_member_count=series_member_count,
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
    duplicates: bool = False,
    series: Literal["collapsed", "all"] = "collapsed",
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[MediaSummary]:
    stmt = select(Media)
    # Revue J1 (🟠) : la grille listait aussi les doublons (`duplicate_of_media_id` non
    # `NULL`), contredisant « deux fichiers identiques sont dédoublonnés » (critère
    # d'acceptation J1). Intégration live J1 : ce filtre par défaut laissait l'onglet
    # « Doublons » structurellement vide, faute de tout moyen de le lever — `duplicates`
    # l'inverse (plutôt que de l'annuler) pour ne jamais mélanger doublons et non-doublons
    # sur la même page, symétrique à `unattached`/`quarantined` ci-dessous. Un doublon reste
    # consultable individuellement via `GET /media/{id}` quel que soit ce paramètre (ex.
    # lien depuis la fiche du maître).
    if duplicates:
        stmt = stmt.where(Media.duplicate_of_media_id.is_not(None))
    else:
        stmt = stmt.where(access.exclude_duplicates_clause(Media.duplicate_of_media_id))
    # Intégration live J1 : `MediaSummary` n'exposait ni `series_id` ni le compte de la
    # série, empêchant la grille de satisfaire « une rafale est regroupée en série et
    # n'affiche qu'un représentant » (critère d'acceptation J1). Par défaut
    # (`series=collapsed`) on ne renvoie que les médias hors série et le représentant de
    # chaque série ; `series=all` renvoie tous les membres (ex. zoom sur une série depuis sa
    # fiche) — nommage symétrique au `series=collapsed|all` déjà prévu pour `GET /search`
    # (§3-K.2 du plan).
    if series == "collapsed":
        # Revue J1 (🔴) : défense en profondeur (voir docstring de
        # `access.series_collapse_clause` — factorisée depuis ce lot précisément parce que
        # `services/facets.py` avait réimplémenté cette règle sans la reprendre).
        stmt = stmt.where(
            access.series_collapse_clause(
                series_id=Media.series_id,
                is_series_representative=Media.is_series_representative,
                shooting_id=Media.shooting_id,
            )
        )
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

    items, next_cursor, total = paginate_by_id(
        db, stmt, Media.id, cursor=cursor, limit=limit, with_total=True
    )

    # Un seul aller-retour pour toute la page plutôt qu'un par média (`member_count` est
    # déjà tenu à jour sur `media_series`, cf. `pipeline/series.py` — pas de N+1 ici).
    series_ids = {m.series_id for m in items if m.series_id is not None}
    member_counts: dict[int, int] = {}
    if series_ids:
        rows = db.execute(
            select(MediaSeries.id, MediaSeries.member_count).where(MediaSeries.id.in_(series_ids))
        ).all()
        for series_id, member_count in rows:
            member_counts[series_id] = member_count

    return Page(
        items=[_to_summary(m, series_member_count=member_counts.get(m.series_id)) for m in items],
        next_cursor=next_cursor,
        total=total,
    )


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
        quarantine_detail=_quarantine_detail(media),
        attachment_status=media.attachment_status,
        attachment_source=media.attachment_source,
        attachment_detail=_attachment_detail(media),
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
    if media.ingest_status == "quarantined":
        # 🟡 : la fixture frontend renvoie déjà `409` pour ce cas (divergence relevée en
        # revue) — un média en quarantaine n'a pas de dérivés fiables (vignette, hash) et
        # ne doit pas pouvoir être rattaché tant que le motif n'est pas résolu.
        raise HTTPException(
            status_code=409,
            detail={
                "code": "media_quarantined",
                "message": "Ce média est en quarantaine — impossible à rattacher.",
                "detail": {"quarantine_reason": media.quarantine_reason},
            },
        )
    shooting = access.get_visible_shooting_or_404(db, user, payload.shooting_id)

    media.shooting_id = shooting.id
    media.attachment_status = "shooting_attached"
    media.attachment_source = "human"
    media.attachment_detail = None
    db.flush()
    project_media(db, media.id)
    db.commit()
    db.refresh(media)
    return _media_out(db, media)


def _engagement_of_media_or_404(db: Session, media: Media, engagement_id: int) -> Engagement:
    """Un engagement n'existe que **pour un shooting donné** (invariant `AGENTS.md`).

    Rattacher un média à un engagement d'un autre événement n'aurait aucun sens métier :
    le n°12 de ce week-end-là n'est pas le n°12 du week-end suivant.
    """
    engagement = db.get(Engagement, engagement_id)
    if engagement is None or engagement.shooting_id != media.shooting_id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Engagement introuvable pour le shooting de ce média.",
                "detail": None,
            },
        )
    return engagement


@router.post(
    "/{media_id}/engagements",
    response_model=MediaEngagementOut,
    status_code=201,
    summary="Rattachement manuel à un engagement (J2, `source='human'`)",
)
def add_media_engagement(
    media_id: int,
    payload: MediaEngagementAttachRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> MediaEngagementOut:
    media = access.get_visible_media_or_404(db, user, media_id)
    if media.shooting_id is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "media_not_attached",
                "message": "Ce média n'est rattaché à aucun shooting : aucun engagement applicable.",
                "detail": None,
            },
        )
    access.assert_can_write_engagements(db, user, media.shooting_id)
    engagement = _engagement_of_media_or_404(db, media, payload.engagement_id)

    # Un média peut porter **plusieurs** rattachements (deux voitures dans le cadre) : la
    # clé primaire composite l'autorise, `ON CONFLICT DO NOTHING` rend l'appel idempotent.
    db.execute(
        pg_insert(MediaEngagement)
        .values(
            media_id=media.id,
            engagement_id=engagement.id,
            source="human",
            confidence=None,
            created_by=user.id,
        )
        .on_conflict_do_nothing(index_elements=["media_id", "engagement_id"])
    )
    media.attachment_status = "engagement_attached"
    media.attachment_source = "human"
    db.flush()
    project_media(db, media.id)
    db.commit()
    return MediaEngagementOut(
        engagement_id=engagement.id,
        car_number=engagement.car_number,
        source="human",
        confidence=None,
    )


@router.delete(
    "/{media_id}/engagements/{engagement_id}",
    status_code=204,
    summary="Retirer un rattachement (J2)",
)
def delete_media_engagement(
    media_id: int, engagement_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> None:
    media = access.get_visible_media_or_404(db, user, media_id)
    if media.shooting_id is not None:
        access.assert_can_write_engagements(db, user, media.shooting_id)
    link = db.get(MediaEngagement, (media_id, engagement_id))
    if link is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Rattachement introuvable.",
                "detail": None,
            },
        )
    db.delete(link)
    db.flush()

    # Revue J2 (🔴 n°1) : rendre la décision humaine **terminale avant** re-projection —
    # sinon `classify.project_media` juste en-dessous recharge le(s) candidat(s) OCR visant
    # `engagement_id`, recalcule `auto`/`accepted` et **réinsère** le rattachement qu'on
    # vient de supprimer, avant même le commit. Même sémantique que `POST /review/decisions`
    # (action `reject`, `pipeline/ocr/classify.py:36-39`), simplement pas branchée sur ce
    # chemin jusqu'ici. Seuls les candidats encore « machine » (`MACHINE_RESOLUTIONS`) sont
    # concernés — un candidat déjà `accepted`/`rejected` reste tel quel, terminal.
    now = datetime.now(UTC)
    db.execute(
        update(MediaOcrCandidate)
        .where(
            MediaOcrCandidate.media_id == media_id,
            MediaOcrCandidate.engagement_id == engagement_id,
            MediaOcrCandidate.resolution.in_(classify.MACHINE_RESOLUTIONS),
        )
        .values(
            resolution=classify.RESOLUTION_REJECTED,
            engagement_id=None,
            resolved_by=user.id,
            resolved_at=now,
        )
    )
    db.flush()

    # Retirer un rattachement ne « détache » pas arbitrairement le média : on rejoue la
    # projection déterministe, qui recalcule `attachment_status` à partir des candidats et
    # des rattachements restants. Un candidat déjà arbitré reste arbitré — retirer le
    # rattachement ne réécrit pas la décision humaine, seulement son effet.
    classify.project_media(db, media, load_ocr_settings(db))

    # Repli pour un média sans aucun candidat OCR (rattachement 100 % manuel) : la
    # projection est alors un no-op délibéré, personne ne recalcule son état — factorisé
    # (revue J2, 🟠 n°2) : c'est la même garde que `DELETE /engagements/{id}` a besoin.
    classify.reconcile_unlinked_attachment_status(db, [media_id])
    db.flush()
    project_media(db, media.id)
    db.commit()


@router.get(
    "/{media_id}/ocr",
    response_model=MediaOcrResponse,
    summary="Candidats OCR bruts du média (J2) — score et boîte, affichés dans l'UI",
)
def get_media_ocr(
    media_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> MediaOcrResponse:
    """Les candidats **bruts**, tels que persistés : c'est la matière première du jalon.

    Ce que le modèle a lu, avec quelle confiance et à quel endroit de l'image, est visible
    dans l'UI — pas seulement la conclusion. C'est ce qui rend le score explicable et ce
    qui permet de rejouer une classification sans jamais relancer une inférence.
    """
    media = access.get_visible_media_or_404(db, user, media_id)
    candidates = db.execute(
        select(MediaOcrCandidate)
        .where(MediaOcrCandidate.media_id == media.id)
        .order_by(MediaOcrCandidate.confidence.desc(), MediaOcrCandidate.id)
    ).scalars()
    return MediaOcrResponse(
        candidates=[
            OcrCandidateOut(
                id=candidate.id,
                raw_text=candidate.raw_text,
                normalized_number=candidate.normalized_number,
                confidence=float(candidate.confidence),
                bbox=OcrBoundingBox.model_validate(candidate.bbox),
                engine_version=candidate.engine_version,
                resolution=candidate.resolution,
                engagement_id=candidate.engagement_id,
            )
            for candidate in candidates
        ]
    )
