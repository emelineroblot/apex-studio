"""Handler `reindex_media` (§3-K du plan, registre §3-E.3) — point d'entrée **asynchrone**
de la projection de recherche.

Aux points d'appel synchrones (ingestion, arbitrage humain, OCR, reclassement, rattachement
manuel), `apex/services/search_projection.py` est appelé **directement**, dans la même
transaction que le changement métier — pas de détour par la file, cohérent avec le principe
« aucun enqueue sans l'écriture qui le justifie » (§3-E.4.2) et avec le constat laissé par
l'agent OCR (« une projection périmée est un média introuvable »).

Ce handler existe pour les deux cas où un appel synchrone n'est pas le bon outil :
- `queue/handlers/reattach_camera.py` et `queue/handlers/finalize_batch.py`, qui
  connaissent déjà l'ensemble des médias à reprojeter et appellent directement
  `search_projection` — ce handler n'est **pas** leur mécanisme, il reste disponible pour
  un déclenchement externe explicite (ex. `apex.cli reindex`, un futur bouton
  « réindexer ce média » côté support) ;
- la réindexation complète (`apex.cli reindex`, sans argument) qui passe par
  `project_media_search(session, None)` directement, hors file, pour rester une commande
  synchrone et scriptable.

Registre (§3-E.3) : priorité 150 (plus basse que l'OCR et le rattachement), `dedupe_key
= "reindex:{media_id}"` — plusieurs déclencheurs successifs pour le même média
convergent vers un seul job en file.
"""

from __future__ import annotations

from typing import Any

from apex.queue.registry import JobContext, handler
from apex.services.search_projection import project_media_search


@handler("reindex_media", max_attempts=3)
def handle_reindex_media(ctx: JobContext) -> dict[str, Any]:
    media_id = ctx.job.payload.get("media_id")
    if media_id is None:
        raise ValueError("payload invalide : « media_id » manquant.")
    touched = project_media_search(ctx.session, [int(media_id)])
    return {"media_id": media_id, "touched": touched}
