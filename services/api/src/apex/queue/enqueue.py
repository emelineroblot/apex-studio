"""Enqueue transactionnel (§3-E.4.2 du plan).

`enqueue()` ne committe jamais lui-même : il doit être appelé **dans la même
transaction** que l'écriture métier qui le justifie (ex. `INSERT media` + enqueue
`ingest_media`, §3-F.4.1). C'est l'appelant qui committe. L'anti-doublon repose sur
l'index unique partiel `job_dedupe_idx` : `INSERT ... ON CONFLICT DO NOTHING`, donc un
rejeu avec le même `dedupe_key` sur un job encore vivant est un no-op silencieux — pas
une exception.

**Correction revue J1 (🟠)** : l'index ne couvre plus que `status = 'pending'` (et non
plus `pending`/`running` comme au plan §3-E.1 initial). Scénario observé avec la portée
`running` incluse : un `finalize_batch` en cours d'exécution occupe le slot de dédoublonnage
« batch:X » ; si le dernier `ingest_media` du lot se termine pendant ce temps, son enqueue
de recalcul est un no-op silencieux — et comme personne ne relance `finalize_batch` une
fois celui-ci passé à `done`, le lot reste `processing` indéfiniment. Un job `running` ne
bloque plus l'enqueue d'un successeur `pending` : au pire, deux exécutions (l'une avec
l'état pré-course, l'autre avec l'état à jour) — sans risque de double-traitement
**concurrent** puisque `FOR UPDATE SKIP LOCKED` (garantie n°1, §3-E.4) reste inchangé, et
sans risque de perte puisqu'un `pending` frais est toujours accepté.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apex.models.job import Job
from apex.queue.registry import get_handler

# Doit correspondre **exactement** au prédicat de l'index unique partiel `job_dedupe_idx`
# (`models/job.py`) : PostgreSQL n'infère une cible `ON CONFLICT` sur un index partiel que
# si le `WHERE` de la clause reproduit celui de l'index — sinon `InvalidColumnReference`
# (« there is no unique or exclusion constraint matching the ON CONFLICT specification »),
# reproduit en conditions réelles lors du premier upload transactionnel.
_DEDUPE_INDEX_WHERE = text("dedupe_key IS NOT NULL AND status = 'pending'")


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    priority: int = 100,
    run_at: datetime | None = None,
    max_attempts: int | None = None,
) -> int | None:
    """Insère un job. Renvoie son `id`, ou `None` si un doublon vivant existait déjà.

    Le flush est explicite (`session.flush()`) pour que l'`id` soit disponible avant le
    `commit()` de l'appelant, sans committer à sa place.

    `max_attempts=None` (défaut) : reporté depuis le `@handler(kind, max_attempts=...)`
    enregistré pour ce `kind` — correction revue J1 (🟠) : avant ce correctif, la ligne
    `job` recevait toujours `3` quel que soit le décorateur (ex. `finalize_batch` déclare
    `5`, obtenait `3` en pratique). Repli sur `3` seulement si le `kind` n'est pas (encore)
    enregistré — ne devrait pas arriver en usage normal (`apex.queue.handlers` est importé
    avant tout enqueue), mais ne doit jamais lever pour autant.
    """
    if max_attempts is None:
        spec = get_handler(kind)
        max_attempts = spec.max_attempts if spec is not None else 3

    values: dict[str, Any] = {
        "kind": kind,
        "payload": payload or {},
        "dedupe_key": dedupe_key,
        "priority": priority,
        "max_attempts": max_attempts,
    }
    if run_at is not None:
        values["run_at"] = run_at

    if dedupe_key is None:
        job = Job(**values)
        session.add(job)
        session.flush()
        return job.id

    # Doublon vivant possible : passage par un INSERT ... ON CONFLICT DO NOTHING,
    # l'index unique partiel `job_dedupe_idx` ne couvrant que pending/running.
    stmt = (
        pg_insert(Job)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["kind", "dedupe_key"], index_where=_DEDUPE_INDEX_WHERE
        )
        .returning(Job.id)
    )
    inserted_id = session.execute(stmt).scalar_one_or_none()
    if inserted_id is not None:
        return int(inserted_id)

    # Rien inséré : soit un doublon vivant existe déjà, soit une coïncidence de conflit
    # sur un autre index — dans notre cas seul `job_dedupe_idx` peut jouer ce rôle.
    return None


def enqueue_unique_pending(session: Session, kind: str, dedupe_key: str) -> int | None:
    """Renvoie l'id du job `pending`/`running` déjà vivant pour ce `(kind, dedupe_key)`.

    Utilitaire de lecture — pratique pour exposer l'id existant à l'appelant (ex.
    `PATCH /cameras/{id}` veut renvoyer `reattach_job_id` même quand il réutilise un job
    déjà en file).

    **Correctif revue J1 (🟠)** : depuis que l'index de dédoublonnage ne couvre plus que
    `status = 'pending'` (cf. `_DEDUPE_INDEX_WHERE` ci-dessus), il est désormais normal
    d'avoir simultanément un job `running` et un job `pending` vivants pour le même
    `(kind, dedupe_key)` — `scalar_one_or_none()` levait alors `MultipleResultsFound`
    (`500` sur `PATCH /cameras/{id}`). On prend le plus récent (`id` décroissant) : c'est
    celui que l'`INSERT ... ON CONFLICT DO NOTHING` vient d'accepter en no-op, donc celui
    que l'appelant veut suivre.
    """
    stmt = (
        select(Job.id)
        .where(
            Job.kind == kind,
            Job.dedupe_key == dedupe_key,
            Job.status.in_(("pending", "running")),
        )
        .order_by(Job.id.desc())
        .limit(1)
    )
    result = session.execute(stmt).scalar_one_or_none()
    return int(result) if result is not None else None
