"""`drain()` — moteur de drainage de la file (§3-E.2, §3-E.5, §3-E.7 du plan).

Un seul module, plusieurs pilotes (§3-E.7) :
- `apex.cli worker --loop` : boucle locale, appelle `drain()` en rafale et dort 500 ms
  quand la file est vide (voir `apex/cli.py`) ;
- `POST /jobs/tick` : appelle `drain()` une fois avec un budget de temps borné
  (serverless, `maxDuration=300`) ;
- `GET /batches/{id}` et `PATCH /cameras/{id}` : déclenchent un tick à budget court après
  chaque enqueue depuis l'API (§3-E.7 (a)), pour que le résultat soit démontrable en ligne
  sans attendre le prochain polling.

**Les pilotes n'ont plus tous les mêmes capacités.** Depuis la préparation du déploiement,
les trois pilotes HTTP tournent dans une fonction Vercel qui n'embarque pas le moteur OCR
(trop lourd pour le plafond de 250 Mo — `docs/wiki/architecture.md`), là où le pilote CLI
tourne sur un poste qui l'a. `drain()` détecte donc ce que *ce* processus sait faire
(`queue.capabilities`) et exclut de la réclamation les types de jobs qu'il ne peut pas
exécuter (`registry.unservable_kinds`). Ces jobs restent `pending`, comptés dans `deferred` :
un pilote incapable les laisse pour un pilote capable, il ne les échoue pas.

Trois garanties de non-double-traitement superposées (§3-E.4) — les deux dernières ont été
corrigées en revue J1 (🔴 n°3) :
1. `FOR UPDATE SKIP LOCKED` + commit immédiat (`claim.claim_batch`).
2. Index unique partiel `(kind, dedupe_key)` sur les jobs `pending` (`queue.enqueue`).
3. **Toute transition d'un job réclamé est gardée par `WHERE id=:id AND
   locked_by=:worker_id`** (`_guarded_transition` ci-dessous) : si un autre processus a
   entre-temps repris ce job (ex. `reap_stale` l'a jugé mort pendant que ce worker
   travaillait encore dessus), l'`UPDATE` affecte 0 ligne et ce worker **abandonne** son
   résultat plutôt que d'écraser l'état déjà repris. Le heartbeat est en outre rafraîchi
   **avant chaque job** du lot (pas seulement une fois à la réclamation) — sans quoi un
   lot de 10 jobs à ~1-3 s chacun peut voir son 10ᵉ job démarrer alors que le heartbeat
   date de plusieurs minutes, et se faire déclarer mort par un `reap_stale` concurrent en
   plein traitement (scénario détaillé en revue).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import Update, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from apex.models.job import Job
from apex.queue.capabilities import available_capabilities
from apex.queue.claim import claim_batch, reap_stale, release_unclaimed
from apex.queue.claim import heartbeat as refresh_heartbeat
from apex.queue.registry import JobContext, get_handler, unservable_kinds

# Backoff des échecs récupérables (§3-E.2) : 5 s, 30 s, 120 s, puis `dead` au-delà de
# `max_attempts`. Indexé par `attempts` (1 = première tentative déjà consommée par
# `claim_batch`, qui incrémente avant traitement).
BACKOFF_SCHEDULE_SECONDS = (5, 30, 120)

DEFAULT_BATCH_SIZE = 10


@dataclass(slots=True)
class DrainResult:
    """Reflète le contrat `TickResponse` (`schemas/job.py`) : `claimed/done/failed/remaining`."""

    claimed: int = 0
    done: int = 0
    failed: int = 0
    dead: int = 0
    requeued: int = 0
    reaped: int = 0
    released: int = 0
    remaining: int = 0
    #: Jobs `pending` dus qu'un pilote plus capable devra traiter — **sous-ensemble de
    #: `remaining`**, pas un compteur disjoint. Zéro sur un worker complet.
    deferred: int = 0
    errors: list[str] = field(default_factory=list)

    def as_tick_response(self) -> dict[str, int]:
        """`failed` du contrat d'API regroupe les échecs terminaux : `failed` + `dead`."""
        return {
            "claimed": self.claimed,
            "done": self.done,
            "failed": self.failed + self.dead,
            "remaining": self.remaining,
            "deferred": self.deferred,
        }


def _backoff_seconds(attempts: int) -> int:
    index = min(max(attempts, 1), len(BACKOFF_SCHEDULE_SECONDS)) - 1
    return BACKOFF_SCHEDULE_SECONDS[index]


def _count_remaining(session: Session) -> int:
    stmt = select(func.count()).select_from(Job).where(Job.status == "pending")
    return int(session.execute(stmt).scalar_one())


def _count_deferred(session: Session, kinds: tuple[str, ...]) -> int:
    """Jobs `pending` que ce pilote a volontairement laissés — `0` s'il sait tout faire."""
    if not kinds:
        return 0
    stmt = select(func.count()).select_from(Job).where(Job.status == "pending", Job.kind.in_(kinds))
    return int(session.execute(stmt).scalar_one())


def _make_heartbeat(job: Job, worker_id: str) -> Callable[[], None]:
    """`ctx.heartbeat()` — à appeler toutes les ~10 s dans les handlers longs (§3-E.5).

    Ne capture volontairement **aucune session** : `claim.heartbeat` écrit sur sa propre
    connexion dédiée (revue J2, 🔴 n°2) — capturer `ctx.session` ici referait exactement
    l'erreur corrigée dans `claim.py`.
    """

    def _heartbeat() -> None:
        refresh_heartbeat(job.id, worker_id)

    return _heartbeat


def _guarded_transition(session: Session, job_id: int, worker_id: str, stmt: Update) -> bool:
    """Applique `stmt` (déjà filtrée sur `Job.id`) en ajoutant la garde `locked_by`
    (§3-E.4, garantie 3). Renvoie `True` si la transition a effectivement été appliquée par
    **ce** worker — `False` si un autre processus détenait déjà le job, auquel cas
    l'appelant doit abandonner son résultat, jamais écraser l'état repris ailleurs.
    """
    outcome = cast(
        CursorResult, session.execute(stmt.where(Job.id == job_id, Job.locked_by == worker_id))
    )
    session.commit()
    return outcome.rowcount > 0


def _process_one(session: Session, job: Job, worker_id: str, result: DrainResult) -> None:
    spec = get_handler(job.kind)
    if spec is None:
        message = f"kind de job inconnu : « {job.kind} » (aucun handler enregistré)"
        applied = _guarded_transition(
            session,
            job.id,
            worker_id,
            update(Job).values(
                status="failed",
                last_error=message,
                locked_by=None,
                updated_at=datetime.now(UTC),
            ),
        )
        if applied:
            result.failed += 1
            result.errors.append(message)
        return

    ctx = JobContext(
        job=job,
        session=session,
        worker_id=worker_id,
        heartbeat=_make_heartbeat(job, worker_id),
    )
    try:
        job_result = spec.func(ctx)
    except Exception as exc:  # noqa: BLE001 — capture volontairement large : un handler
        # ne doit jamais planter le worker, quelle que soit l'erreur.
        message = f"{type(exc).__name__}: {exc}"
        # Un handler qui lève après un `flush()` en échec (ex. contrainte DB) laisse la
        # session en « pending rollback » : tout `commit()` ultérieur lève à son tour et
        # crashe le worker au lieu de consigner l'échec — reproduit en conditions réelles
        # (`NumericValueOutOfRange` sur un `flush()` intermédiaire). Rollback explicite
        # avant de rouvrir une transaction propre, puis on ré-attache `job` (le rollback
        # expire les instances de la session).
        session.rollback()
        refreshed = session.get(Job, job.id)
        if refreshed is None:
            result.errors.append(message)
            return
        job = refreshed
        if job.attempts >= job.max_attempts:
            applied = _guarded_transition(
                session,
                job.id,
                worker_id,
                update(Job).values(
                    status="dead",
                    last_error=message,
                    locked_by=None,
                    updated_at=datetime.now(UTC),
                ),
            )
            if not applied:
                result.errors.append(message)
                return
            result.dead += 1
            # §3-E.5 / revue J1 (🔴 n°1) : un job mort par épuisement des tentatives doit
            # produire le même effet métier qu'un job mort repris par `reap_stale`
            # (`claim.reap_stale` dispatche déjà `on_dead` sur son propre chemin) — sans
            # quoi un média reste indéfiniment `uploaded`/`processing`, hors de tout bac.
            if spec.on_dead is not None:
                # Recharge explicitement l'objet depuis la base : `_guarded_transition` a
                # écrit `status`/`last_error` via un `UPDATE` Core, pas une affectation
                # ORM — `on_dead` doit voir la valeur définitive de `last_error`, jamais
                # un attribut resté à sa valeur pré-transition.
                session.refresh(job)
                try:
                    spec.on_dead(session, job)
                    session.commit()
                except Exception:  # noqa: BLE001 — cf. `claim.reap_stale` : un hook
                    # `on_dead` défaillant ne doit jamais empêcher le reste du drainage.
                    session.rollback()
        else:
            applied = _guarded_transition(
                session,
                job.id,
                worker_id,
                update(Job).values(
                    status="pending",
                    run_at=datetime.now(UTC) + timedelta(seconds=_backoff_seconds(job.attempts)),
                    last_error=message,
                    locked_by=None,
                    locked_at=None,
                    heartbeat_at=None,
                    updated_at=datetime.now(UTC),
                ),
            )
            if not applied:
                result.errors.append(message)
                return
            result.requeued += 1
        result.errors.append(message)
        return

    applied = _guarded_transition(
        session,
        job.id,
        worker_id,
        update(Job).values(
            status="done",
            result=job_result,
            locked_by=None,
            heartbeat_at=None,
            updated_at=datetime.now(UTC),
        ),
    )
    if applied:
        result.done += 1
    else:
        result.errors.append(
            f"job {job.id} : résultat abandonné, repris par un autre worker en cours de traitement"
        )


def drain(
    session_factory: Callable[[], Session],
    worker_id: str,
    *,
    deadline: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    excluded_kinds: tuple[str, ...] | None = None,
) -> DrainResult:
    """Draine la file jusqu'à épuisement ou `deadline` (§3-E.7) — jamais indéfiniment.

    `deadline=None` : draine jusqu'à épuisement de la file puis s'arrête (usage : un
    tick « once »). Ne poll **jamais** en boucle infinie ici — c'est le pilote CLI
    (`--loop`) qui répète les appels avec un sommeil à vide, jamais ce module.

    `excluded_kinds=None` (défaut) : déduit des capacités réelles du processus courant —
    aucun pilote n'a à savoir quoi exclure, ni à être configuré pour. Un tuple explicite
    (y compris vide) court-circuite la détection : réservé aux tests, qui doivent pouvoir
    simuler un environnement sans dépendre de ce qui est installé sur la machine.
    """
    if excluded_kinds is None:
        excluded_kinds = unservable_kinds(available_capabilities())
    session = session_factory()
    result = DrainResult()
    try:
        result.reaped = reap_stale(session)

        while True:
            if deadline is not None and datetime.now(UTC) >= deadline:
                break

            batch = claim_batch(session, worker_id, batch_size, excluded_kinds=excluded_kinds)
            if not batch:
                break

            result.claimed += len(batch)
            for index, job in enumerate(batch):
                if deadline is not None and datetime.now(UTC) >= deadline:
                    # Budget de temps épuisé en cours de lot (revue J1, 🔴 n°2) : les jobs
                    # restants ont été réclamés (`attempts` déjà incrémenté par
                    # `claim_batch`) mais jamais exécutés — les relâcher explicitement en
                    # `pending` avec `attempts` décrémenté, plutôt que les laisser
                    # `running` jusqu'à un hypothétique `reap_stale` 3 minutes plus tard.
                    # Sans ce correctif, une réclamation sans exécution consomme une
                    # tentative : au bout de `max_attempts` cycles de polling passés à
                    # réclamer-puis-abandonner, des photos jamais ouvertes finissent en
                    # quarantaine.
                    result.released += release_unclaimed(session, batch[index:], worker_id)
                    break
                # §3-E.5 / revue J1 (🔴 n°3) : rafraîchit le heartbeat avant CHAQUE job du
                # lot, pas seulement une fois à la réclamation — un lot de 10 jobs à
                # 1-3 s/job peut voir son dernier job démarrer plusieurs minutes après la
                # réclamation initiale.
                refresh_heartbeat(job.id, worker_id)
                _process_one(session, job, worker_id, result)

        result.remaining = _count_remaining(session)
        result.deferred = _count_deferred(session, excluded_kinds)
        return result
    finally:
        session.close()
