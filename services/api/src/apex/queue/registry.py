"""Registre des types de jobs (§3-E.3 du plan) — enregistrement par décorateur.

Vide de tout handler métier à ce stade (lot 0/2) : les handlers réels (`ingest_media`,
`finalize_batch`, `reattach_camera`, `sweep_orphans`, puis l'OCR en J2, la livraison en
J3, …) s'enregistrent ici au fur et à mesure des lots suivants, dans
`apex/queue/handlers/`. Un `kind` inconnu au moment de la réclamation échoue
explicitement (`status='failed'`) — jamais de silence (§3-E.3).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from apex.models.job import Job


@dataclass(frozen=True, slots=True)
class JobContext:
    """Passé à chaque handler — porte la session et le moyen de signaler un heartbeat.

    Les handlers longs (`build_delivery`, `demo_reset`, J2/J3) doivent appeler
    `heartbeat()` toutes les ~10 s (§3-E.5) : c'est ce qui permet à `reap_stale` de
    distinguer un job vivant d'un job mort après un timeout serverless.
    """

    job: Job
    session: Session
    worker_id: str
    heartbeat: Callable[[], None]


# Signature d'un handler : reçoit le contexte, renvoie un résultat JSON-sérialisable
# (persisté dans `job.result`) ou `None`.
HandlerFunc = Callable[[JobContext], dict[str, Any] | None]

# Appelé quand un job de ce `kind` passe à `dead` (retries épuisés) **par `reap_stale`**
# (worker mort/silencieux, §3-E.5) — reçoit `(session, job)`, dans la même transaction que
# la bascule `dead`. Doit produire un effet métier lisible (ex. quarantaine) : « aucun job
# mort ne laisse un objet métier dans un état intermédiaire » (§3-E.5).
OnDeadFunc = Callable[["Session", "Job"], None]


@dataclass(frozen=True, slots=True)
class HandlerSpec:
    kind: str
    func: HandlerFunc
    max_attempts: int
    on_dead: OnDeadFunc | None = None


_REGISTRY: dict[str, HandlerSpec] = {}


def handler(
    kind: str, *, max_attempts: int = 3, on_dead: OnDeadFunc | None = None
) -> Callable[[HandlerFunc], HandlerFunc]:
    """Décorateur d'enregistrement — `@handler("ingest_media", max_attempts=3)`."""

    def decorator(func: HandlerFunc) -> HandlerFunc:
        if kind in _REGISTRY:
            raise ValueError(f"Handler déjà enregistré pour le type de job « {kind} ».")
        _REGISTRY[kind] = HandlerSpec(
            kind=kind, func=func, max_attempts=max_attempts, on_dead=on_dead
        )
        return func

    return decorator


def get_handler(kind: str) -> HandlerSpec | None:
    """`None` si le type de job est inconnu — l'appelant doit alors échouer explicitement."""
    return _REGISTRY.get(kind)


def registered_kinds() -> list[str]:
    return sorted(_REGISTRY)


def _reset_registry_for_tests() -> None:
    """Réservé aux tests : vide le registre entre deux scénarios isolés."""
    _REGISTRY.clear()
