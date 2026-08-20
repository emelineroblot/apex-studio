"""Rattachement temporel (§3-F.3) — `shooting.period @> media.shot_at`, index GiST.

Trois cas, tous explicites : 0 shooting → bac « à rattacher » ; 1 shooting → rattaché ;
≥ 2 shootings → désambiguïsation par `shooting_staff` (le photographe qui a déposé le
média), sinon bac « à rattacher » avec les candidats listés pour trancher en un clic.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.models.media import Media
from apex.models.shooting import Shooting, ShootingStaff


def find_candidate_shootings(session: Session, shot_at: datetime) -> list[Shooting]:
    stmt = select(Shooting).where(Shooting.period.contains(shot_at)).order_by(Shooting.id)
    return list(session.execute(stmt).scalars().all())


def attach_media_by_time(session: Session, media: Media) -> None:
    """Mute `media.attachment_status/shooting_id/attachment_source/attachment_detail`.

    Ne committe jamais (l'appelant — `ingest_media` — possède la transaction, §3-E.4.2).
    """
    if media.shot_at is None:
        media.attachment_status = "unattached"
        media.shooting_id = None
        media.attachment_source = None
        media.attachment_detail = {"reason": "no_exif_timestamp"}
        return

    candidates = find_candidate_shootings(session, media.shot_at)

    if len(candidates) == 0:
        media.attachment_status = "unattached"
        media.shooting_id = None
        media.attachment_source = None
        media.attachment_detail = {"reason": "no_matching_window"}
        return

    if len(candidates) == 1:
        _attach(media, candidates[0], source="pipeline_time")
        return

    # ≥ 2 shootings chevauchants : ne garder que ceux où le déposant est affecté.
    uploader_shootings = set(
        session.execute(
            select(ShootingStaff.shooting_id).where(ShootingStaff.user_id == media.uploaded_by)
        ).scalars()
    )
    narrowed = [s for s in candidates if s.id in uploader_shootings]

    if len(narrowed) == 1:
        _attach(media, narrowed[0], source="pipeline_time")
        return

    media.attachment_status = "unattached"
    media.shooting_id = None
    media.attachment_source = None
    media.attachment_detail = {
        "reason": "ambiguous_window",
        "candidate_shooting_ids": [s.id for s in candidates],
    }


def _attach(media: Media, shooting: Shooting, *, source: str) -> None:
    media.shooting_id = shooting.id
    media.attachment_status = "shooting_attached"
    media.attachment_source = source
    media.attachment_detail = None
