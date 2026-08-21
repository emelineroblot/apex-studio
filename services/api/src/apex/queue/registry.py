"""Registre des types de jobs (§3-E.3 du plan) — enregistrement par décorateur.

Vide de tout handler métier à ce stade (lot 0/2) : les handlers réels (`ingest_media`,
`finalize_batch`, `reattach_camera`, `sweep_orphans`, puis l'OCR en J2, la livraison en
J3, …) s'enregistrent ici au fur et à mesure des lots suivants, dans
`apex/queue/handlers/`. Un `kind` inconnu au moment de la réclamation échoue
explicitement (`status='failed'`) — jamais de silence (§3-E.3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
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
    #: Capacités d'exécution exigées par ce handler (`queue.capabilities`). Un pilote qui
    #: ne les a pas toutes ne **réclame jamais** ce type de job — il le laisse en file
    #: pour un pilote capable, plutôt que de l'échouer trois fois puis de le tuer.
    requires: frozenset[str] = frozenset()


_REGISTRY: dict[str, HandlerSpec] = {}


def handler(
    kind: str,
    *,
    max_attempts: int = 3,
    on_dead: OnDeadFunc | None = None,
    requires: Iterable[str] = (),
) -> Callable[[HandlerFunc], HandlerFunc]:
    """Décorateur d'enregistrement — `@handler("ingest_media", max_attempts=3)`.

    `requires` déclare les capacités d'exécution nécessaires (`queue.capabilities`) :
    `@handler("ocr_media", requires=(OCR_ENGINE,))` rend ce job invisible des pilotes qui
    n'embarquent pas le moteur OCR, sans que ces pilotes aient à connaître son existence.
    """

    def decorator(func: HandlerFunc) -> HandlerFunc:
        if kind in _REGISTRY:
            raise ValueError(f"Handler déjà enregistré pour le type de job « {kind} ».")
        _REGISTRY[kind] = HandlerSpec(
            kind=kind,
            func=func,
            max_attempts=max_attempts,
            on_dead=on_dead,
            requires=frozenset(requires),
        )
        return func

    return decorator


def get_handler(kind: str) -> HandlerSpec | None:
    """`None` si le type de job est inconnu — l'appelant doit alors échouer explicitement."""
    return _REGISTRY.get(kind)


def registered_kinds() -> list[str]:
    return sorted(_REGISTRY)


def unservable_kinds(capabilities: frozenset[str]) -> tuple[str, ...]:
    """Types de jobs **enregistrés** qu'un processus doté de `capabilities` ne peut pas
    exécuter — à exclure de la réclamation (`claim.claim_batch`).

    Une exclusion, jamais une liste blanche : un `kind` **inconnu** du registre doit rester
    réclamable pour échouer explicitement (§3-E.3, `runner._process_one`). Filtrer par
    inclusion le rendrait invisible et le laisserait dormir en file — exactement le silence
    que la règle interdit.
    """
    return tuple(
        sorted(kind for kind, spec in _REGISTRY.items() if not spec.requires <= capabilities)
    )


def _reset_registry_for_tests() -> None:
    """Réservé aux tests : vide le registre entre deux scénarios isolés."""
    _REGISTRY.clear()
