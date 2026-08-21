"""Handler `demo_reset` (§3-N.2 du plan) — réinitialisation nocturne du jeu de démonstration.

Câblé ici en J2 pour que `POST /demo/seed` (contrat J2, `{reset: bool} -> {job_id}`) ait un
handler réel plutôt qu'un job qui échouerait « kind inconnu » (§3-E.3, jamais de silence).
Le déclenchement **automatique** (cron `0 3 * * *` → `/api/cron/nightly`, filet de sécurité
« `last_demo_reset` > 24 h ») est du ressort de J3 (§3-N.2) — ce handler, lui, est déjà la
pièce que ce cron appellera : `apex/demo/seed.py::run_seed` dans **une seule transaction**
(« soit tout est restauré, soit rien ne bouge »).
"""

from __future__ import annotations

from typing import Any

from apex.demo.seed import run_seed
from apex.queue.registry import JobContext, handler


@handler("demo_reset", max_attempts=3)
def handle_demo_reset(ctx: JobContext) -> dict[str, Any]:
    reset = bool(ctx.job.payload.get("reset", True))
    result = run_seed(ctx.session, reset=reset, heartbeat=ctx.heartbeat)
    return {
        "reset": result.reset,
        "ran": result.ran,
        "simulated_media": result.simulated_media,
        "real_media": result.real_media,
        "real_photos_skipped_reason": result.real_photos_skipped_reason,
        "duration_ms": result.duration_ms,
        "attachment_status_counts": result.attachment_status_counts,
    }
