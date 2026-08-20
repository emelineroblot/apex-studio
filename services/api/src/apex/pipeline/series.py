"""Regroupement des rafales en séries (§3-G.3) — balayage linéaire par (shooting, boîtier),
trié par `shot_at`. Exécuté dans `finalize_batch`, pas dans `ingest_media` (une rafale est
un phénomène qui s'observe une fois plusieurs médias du lot déjà ingérés).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.models.media import Media, MediaSeries
from apex.pipeline.phash import hamming_distance

MIN_SERIES_MEMBERS = 2


def regroup_bursts_for_shooting(
    session: Session,
    shooting_id: int,
    *,
    burst_gap_seconds: float,
    phash_max_distance: int,
) -> int:
    """Reconstruit les séries d'un shooting. Idempotent (§E.6) : recalcule tout à chaque
    appel plutôt que d'incrémenter — un rejeu de `finalize_batch` produit le même résultat.

    Renvoie le nombre de séries matérialisées (>= 2 membres).
    """
    stmt = (
        select(Media)
        .where(
            Media.shooting_id == shooting_id,
            Media.ingest_status == "ingested",
            Media.duplicate_of_media_id.is_(None),
            Media.shot_at.is_not(None),
        )
        .order_by(Media.camera_id, Media.shot_at, Media.id)
    )
    medias = list(session.execute(stmt).scalars().all())

    # Réinitialise le regroupement précédent — idempotence (§E.6).
    for media in medias:
        media.series_id = None
        media.is_series_representative = False
    session.flush()

    existing_series = (
        session.execute(select(MediaSeries).where(MediaSeries.shooting_id == shooting_id))
        .scalars()
        .all()
    )
    for series in existing_series:
        session.delete(series)
    session.flush()

    materialized = 0
    current_camera: int | None = None
    bucket: list[Media] = []

    def _flush_bucket() -> None:
        nonlocal materialized
        if len(bucket) < MIN_SERIES_MEMBERS:
            return
        if bucket[0].camera_id is None:
            # 🟡 : les médias sans boîtier identifié partagent tous `camera_id IS NULL` —
            # sans cette garde, deux boîtiers inconnus différents pourraient être regroupés
            # en une fausse rafale (le tri par `(camera_id, shot_at, id)` les place à la
            # suite les uns des autres, indiscernables une fois le camera_id perdu).
            return
        representative = max(
            bucket,
            key=lambda m: (
                m.sharpness if m.sharpness is not None else float("-inf"),
                -m.shot_at.timestamp() if m.shot_at else 0,
                -m.id,
            ),
        )
        series = MediaSeries(
            shooting_id=shooting_id,
            camera_id=bucket[0].camera_id,
            started_at=bucket[0].shot_at,
            ended_at=bucket[-1].shot_at,
            representative_media_id=None,
            member_count=len(bucket),
        )
        session.add(series)
        session.flush()
        series.representative_media_id = representative.id
        for member in bucket:
            member.series_id = series.id
            member.is_series_representative = member.id == representative.id
        materialized += 1

    previous: Media | None = None
    for media in medias:
        if media.camera_id != current_camera:
            _flush_bucket()
            bucket = []
            current_camera = media.camera_id
            previous = None

        if previous is None:
            bucket = [media]
        else:
            gap = (media.shot_at - previous.shot_at).total_seconds()  # type: ignore[operator]
            same_burst = gap <= burst_gap_seconds and (
                media.phash is None
                or previous.phash is None
                or hamming_distance(media.phash, previous.phash) <= phash_max_distance
            )
            if same_burst:
                bucket.append(media)
            else:
                _flush_bucket()
                bucket = [media]
        previous = media

    _flush_bucket()
    return materialized
