"""Handler `reclassify_ocr` (§3-J.4) — **le job qui ne réveille jamais le modèle**.

Changer un seuil ne relance pas l'inférence : ce handler re-projette les
`media_ocr_candidate` **déjà persistés** dans les bacs auto / validation / abstention, et
laisse intacts les arbitrages humains. Sur 8 000 médias, c'est quelques secondes — contre
plusieurs heures s'il fallait relire chaque image.

Ce module **n'importe pas** `apex.pipeline.ocr.engine`, et c'est structurel : un test
(`tests/ocr/test_reclassify.py`) échoue si l'import réapparaît, et un second injecte un
moteur qui explose à la première lecture pour prouver qu'aucune inférence n'a lieu.

Traitement par tranches avec heartbeat : le job peut porter sur tout le catalogue et doit
survivre au seuil de 3 minutes de `reap_stale` (§3-E.5).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from apex.models.media import Media
from apex.models.search import MediaOcrCandidate
from apex.pipeline.ocr.classify import project_media_batch
from apex.queue.registry import JobContext, handler
from apex.services.ocr_settings import load_ocr_settings

#: Taille de tranche : compromis entre le coût des `IN (...)` et la fréquence du heartbeat.
CHUNK_SIZE = 500


@handler("reclassify_ocr", max_attempts=3)
def handle_reclassify_ocr(ctx: JobContext) -> dict[str, Any]:
    session = ctx.session
    shooting_id = ctx.job.payload.get("shooting_id")

    ocr_settings = load_ocr_settings(session)

    stmt = (
        select(MediaOcrCandidate.media_id)
        .join(Media, Media.id == MediaOcrCandidate.media_id)
        .distinct()
        .order_by(MediaOcrCandidate.media_id)
    )
    if shooting_id is not None:
        stmt = stmt.where(Media.shooting_id == shooting_id)
    media_ids = [int(row) for row in session.execute(stmt).scalars()]

    totals: dict[str, int] = {}
    media_touched = 0
    attached = 0
    detached = 0

    for start in range(0, len(media_ids), CHUNK_SIZE):
        ctx.heartbeat()
        chunk = media_ids[start : start + CHUNK_SIZE]
        result = project_media_batch(session, chunk, ocr_settings)
        media_touched += result.media_touched
        attached += result.attached
        detached += result.detached
        for resolution, count in result.counts.items():
            totals[resolution] = totals.get(resolution, 0) + count

    return {
        "high": ocr_settings.high,
        "low": ocr_settings.low,
        "media_touched": media_touched,
        "attached": attached,
        "detached": detached,
        "resolutions": totals,
        # Signature explicite dans le journal des jobs : ce handler ne lit aucune image.
        "inference_runs": 0,
    }
