"""Handler `reattach_camera` (§3-F.3) — décalage d'horloge rétroactif : recalcule
`shot_at` et rejoue `attach_time` pour **tous** les médias ingérés du boîtier. Trace dans
`job.result` le nombre de médias dont le rattachement a changé — c'est ce chiffre que l'UI
affiche (« N photos re-rattachées »), le critère d'acceptation le rend démontrable.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from apex.models.catalog import Camera
from apex.models.media import Media
from apex.pipeline import attach_time
from apex.pipeline.exif import compute_shot_at
from apex.queue.registry import JobContext, handler


@handler("reattach_camera", max_attempts=3)
def handle_reattach_camera(ctx: JobContext) -> dict[str, Any]:
    camera_id = ctx.job.payload.get("camera_id")
    if camera_id is None:
        raise ValueError("payload invalide : « camera_id » manquant.")

    session = ctx.session
    camera = session.get(Camera, camera_id)
    if camera is None:
        return {"checked": 0, "reattached": 0}

    medias = list(
        session.execute(
            select(Media).where(
                Media.camera_id == camera_id,
                Media.ingest_status == "ingested",
                # Revue J1 (🟠) : un doublon mirror l'état de son maître à l'ingestion
                # (`pipeline/ingest.py`) — le recalculer ici lui donnerait un rattachement
                # propre, ce qui le rendrait visible dans la grille au même titre qu'un
                # original, contredisant « un doublon n'affiche qu'un représentant » (§3-G).
                Media.duplicate_of_media_id.is_(None),
            )
        ).scalars()
    )

    reattached = 0
    for media in medias:
        previous_shooting_id = media.shooting_id
        previous_attachment_status = media.attachment_status

        media.shot_at = compute_shot_at(media.shot_at_exif, camera)
        attach_time.attach_media_by_time(session, media)

        if (
            media.shooting_id != previous_shooting_id
            or media.attachment_status != previous_attachment_status
        ):
            reattached += 1

    session.flush()
    return {"checked": len(medias), "reattached": reattached}
