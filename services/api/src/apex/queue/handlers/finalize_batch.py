"""Handler `finalize_batch` (§3-F.1, §3-F.4.5, §3-G.3) — recalcule les compteurs du lot par
agrégat (jamais un incrément, §E.6 idempotence), regroupe les rafales en séries, et clôt le
lot (`status='closed'`) une fois tous les médias annoncés arrivés à un état terminal.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from apex.models.media import Media, UploadBatch
from apex.pipeline.series import regroup_bursts_for_shooting
from apex.queue.registry import JobContext, handler
from apex.services.app_settings import get_burst_gap_seconds, get_phash_max_distance

TERMINAL_INGEST_STATUSES = ("ingested", "quarantined")


@handler("finalize_batch", max_attempts=5)
def handle_finalize_batch(ctx: JobContext) -> dict[str, Any]:
    batch_id = ctx.job.payload.get("batch_id")
    if batch_id is None:
        raise ValueError("payload invalide : « batch_id » manquant.")

    session = ctx.session
    batch = session.get(UploadBatch, batch_id)
    if batch is None:
        return {"skipped": True, "reason": "batch introuvable"}

    # Réconciliation (§3-F.4.5) : recalculée par agrégat, jamais incrémentée (§E.6).
    received_count = session.execute(
        select(func.count()).select_from(Media).where(Media.batch_id == batch_id)
    ).scalar_one()
    pending_count = session.execute(
        select(func.count())
        .select_from(Media)
        .where(Media.batch_id == batch_id, Media.ingest_status.not_in(TERMINAL_INGEST_STATUSES))
    ).scalar_one()
    batch.received_count = received_count

    # Regroupement des rafales (§3-G.3) — sur chaque shooting touché par ce lot.
    shooting_ids: set[int] = {
        sid
        for sid in session.execute(
            select(Media.shooting_id).where(
                Media.batch_id == batch_id, Media.shooting_id.is_not(None)
            )
        ).scalars()
        if sid is not None
    }
    burst_gap = get_burst_gap_seconds(session)
    phash_max_distance = get_phash_max_distance(session)
    series_created = 0
    for shooting_id in shooting_ids:
        series_created += regroup_bursts_for_shooting(
            session,
            shooting_id,
            burst_gap_seconds=burst_gap,
            phash_max_distance=phash_max_distance,
        )

    closed = False
    if (
        batch.status == "processing"
        and pending_count == 0
        and received_count >= batch.expected_count
    ):
        batch.status = "closed"
        closed = True

    session.flush()
    return {
        "received_count": received_count,
        "pending_count": pending_count,
        "series_created": series_created,
        "closed": closed,
    }
