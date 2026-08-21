"""Handler `reattach_camera` (§3-F.3) — décalage d'horloge rétroactif : recalcule
`shot_at` et rejoue `attach_time` pour **tous** les médias ingérés du boîtier. Trace dans
`job.result` le nombre de médias dont le rattachement a changé — c'est ce chiffre que l'UI
affiche (« N photos re-rattachées »), le critère d'acceptation le rend démontrable.

**Correctif revue J1 (🔴)** : `attach_media_by_time` ne touche jamais `series_id` /
`is_series_representative` — un média qui quitte un shooting (rafale déjà groupée) gardait
donc l'appartenance à son ancienne série, orpheline. Comme `regroup_bursts_for_shooting`
(`pipeline/series.py`) ne requalifie que les médias **actuellement** dans le shooting
interrogé, il ne pouvait jamais rattraper un média déjà détaché (son `shooting_id` a déjà
changé au moment où on le rejouerait). On efface donc `series_id` explicitement ici dès
qu'un média change de shooting, puis on rejoue le regroupement sur l'union des shootings
de départ et d'arrivée touchés par ce recalcul — ça reforme les séries des deux côtés
(celui que le média quitte et celui qu'il rejoint, y compris quand ce dernier n'avait pas
encore de série).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from apex.models.catalog import Camera
from apex.models.media import Media
from apex.models.search import MediaOcrCandidate
from apex.pipeline import attach_time
from apex.pipeline.exif import compute_shot_at
from apex.pipeline.ocr.classify import project_media_batch
from apex.pipeline.series import regroup_bursts_for_shooting
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, handler
from apex.services.app_settings import get_burst_gap_seconds, get_phash_max_distance
from apex.services.ocr_settings import load_ocr_settings
from apex.services.search_projection import (
    project_media_search,
    project_media_search_for_shooting,
)


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
    affected_shooting_ids: set[int] = set()
    # J2 : médias qui changent de shooting — leurs candidats OCR ont été résolus contre la
    # table des engagements de l'**ancien** shooting et n'ont plus de sens. On les
    # re-projette (déterministe, sans ré-inférence) et on ne relance le modèle que pour
    # ceux qui n'ont encore jamais été lus.
    moved_media_ids: list[int] = []
    for media in medias:
        previous_shooting_id = media.shooting_id
        previous_attachment_status = media.attachment_status

        media.shot_at = compute_shot_at(media.shot_at_exif, camera)
        attach_time.attach_media_by_time(session, media)

        if media.shooting_id != previous_shooting_id:
            # 🔴 : le média change de shooting (ou en sort) — son éventuelle appartenance à
            # une série n'est plus valable dans aucun des deux cas tant que le regroupement
            # n'a pas été rejoué. On l'efface immédiatement plutôt que de compter sur
            # `regroup_bursts_for_shooting`, qui ne verra jamais ce média côté « départ »
            # (son `shooting_id` a déjà changé) s'il devient `unattached`.
            media.series_id = None
            media.is_series_representative = False
            moved_media_ids.append(media.id)
            if previous_shooting_id is not None:
                affected_shooting_ids.add(previous_shooting_id)
            if media.shooting_id is not None:
                affected_shooting_ids.add(media.shooting_id)

        if (
            media.shooting_id != previous_shooting_id
            or media.attachment_status != previous_attachment_status
        ):
            reattached += 1

    session.flush()

    ocr_enqueued = 0
    if moved_media_ids:
        ocr_settings = load_ocr_settings(session)
        # Re-projection déterministe : un média qui a quitté son shooting perd ses
        # rattachements OCR ; un média qui en rejoint un voit ses candidats re-confrontés
        # à la nouvelle table des engagements. Aucune image n'est relue ici.
        project_media_batch(session, moved_media_ids, ocr_settings)

        already_read = set(
            session.execute(
                select(MediaOcrCandidate.media_id).where(
                    MediaOcrCandidate.media_id.in_(moved_media_ids)
                )
            ).scalars()
        )
        for media_id in moved_media_ids:
            moved = session.get(Media, media_id)
            if moved is None or moved.shooting_id is None or media_id in already_read:
                continue
            # Jamais lu jusqu'ici (il était dans le bac « à rattacher ») : c'est le seul
            # cas qui justifie une inférence.
            if enqueue(
                session,
                "ocr_media",
                {"media_id": media_id},
                dedupe_key=f"ocr:{media_id}",
                priority=110,
            ):
                ocr_enqueued += 1
        session.flush()

    if affected_shooting_ids:
        burst_gap = get_burst_gap_seconds(session)
        phash_max_distance = get_phash_max_distance(session)
        for shooting_id in affected_shooting_ids:
            regroup_bursts_for_shooting(
                session,
                shooting_id,
                burst_gap_seconds=burst_gap,
                phash_max_distance=phash_max_distance,
            )
        session.flush()

    # §3-F.3 : `shot_at` et `attachment_status` viennent de bouger pour tout le parc du
    # boîtier — la projection de recherche doit suivre, sans quoi le recalage rend des
    # médias introuvables plutôt que re-rattachés (constat laissé par l'agent OCR).
    if medias:
        project_media_search(session, [m.id for m in medias])
    # Le regroupement des rafales (ci-dessus) touche potentiellement des médias d'un autre
    # boîtier du **même** shooting (il efface/reconstruit toutes les séries du shooting) :
    # une réindexation par shooting complet, pas seulement par les médias de ce boîtier.
    for shooting_id in affected_shooting_ids:
        project_media_search_for_shooting(session, shooting_id)

    return {"checked": len(medias), "reattached": reattached, "ocr_enqueued": ocr_enqueued}
