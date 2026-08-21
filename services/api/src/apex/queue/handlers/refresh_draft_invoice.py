"""Handler `refresh_draft_invoice` (§3-O, registre §3-E.3).

Recompose la facture **brouillon** d'une sélection validée. Passe par la file plutôt que
par un appel synchrone dans la route de validation pour une raison précise : la validation
d'une sélection doit répondre tout de suite au client, et rien de ce qu'elle déclenche —
préparation de l'archive, facture — ne doit pouvoir la faire échouer sous ses yeux.

Le travail réel vit dans `services/invoicing.py` ; ce handler n'est qu'un point d'entrée
asynchrone, comme `reindex_media` l'est pour la projection de recherche.
"""

from __future__ import annotations

from typing import Any

from apex.queue.registry import JobContext, handler
from apex.services.invoicing import refresh_draft_invoice


@handler("refresh_draft_invoice", max_attempts=3)
def handle_refresh_draft_invoice(ctx: JobContext) -> dict[str, Any]:
    selection_id = ctx.job.payload.get("selection_id")
    if selection_id is None:
        raise ValueError("payload invalide : « selection_id » manquant.")

    invoice = refresh_draft_invoice(ctx.session, int(selection_id))
    ctx.session.commit()
    if invoice is None:
        # Sélection non validée, ou collection disparue : rien à facturer. Ce n'est pas un
        # échec — le job a fait exactement ce qu'il devait, c'est-à-dire rien.
        return {"selection_id": int(selection_id), "invoice_id": None}
    return {
        "selection_id": int(selection_id),
        "invoice_id": invoice.id,
        "status": invoice.status,
        "total_cents": invoice.total_cents,
    }
