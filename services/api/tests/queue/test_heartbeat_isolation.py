"""`ctx.heartbeat()` ne committe jamais le travail métier en cours (revue J2, 🔴 n°2).

`_make_heartbeat` (`queue/runner.py`) capturait auparavant `ctx.session` : `heartbeat()`
exécutait un `UPDATE` sur cette session puis un `session.commit()` — committant du même
coup tout le travail non encore validé du handler, silencieusement. Reproduit ici sans
mock : le handler modifie une ligne, appelle `ctx.heartbeat()`, puis vérifie **depuis une
connexion indépendante** (donc dans une transaction distincte) que la modification n'est
pas visible avant que le handler ne se termine réellement.
"""

from __future__ import annotations

from sqlalchemy import select

from apex.db import SessionLocal, engine
from apex.models.user import AppUser
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, handler
from apex.queue.runner import drain

_PROBE_KIND = "test_heartbeat_isolation_probe"
_RENAMED_VALUE = "renommé en cours de job — pas encore committé"

#: Rempli par le handler pendant son exécution (thread unique ici, pas de course) —
#: `drain()` ne renvoie aucun résultat par job, seulement un compte-rendu agrégé.
_observed_visible_before_completion: list[bool] = []


@handler(_PROBE_KIND, max_attempts=1)
def _probe(ctx: JobContext) -> dict[str, bool]:
    user = ctx.session.get(AppUser, ctx.job.payload["user_id"])
    assert user is not None
    user.full_name = _RENAMED_VALUE
    ctx.session.flush()  # visible dans CETTE session, pas encore committé en base

    ctx.heartbeat()

    # Connexion neuve, indépendante de `ctx.session` : si `ctx.heartbeat()` avait committé
    # la transaction du handler (le bug corrigé), le renommage serait déjà visible ici.
    with engine.connect() as conn:
        current_name = conn.execute(
            select(AppUser.full_name).where(AppUser.id == user.id)
        ).scalar_one()
    _observed_visible_before_completion.append(current_name == _RENAMED_VALUE)

    return {"probed": True}


def test_heartbeat_does_not_commit_the_handlers_pending_transaction(db_session) -> None:
    user = AppUser(
        email="heartbeat-isolation@apex-test.dev",
        password_hash="x",
        full_name="avant le job",
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    _observed_visible_before_completion.clear()
    enqueue(
        db_session,
        _PROBE_KIND,
        {"user_id": user.id},
        dedupe_key="heartbeat-isolation-probe",
    )
    db_session.commit()

    result = drain(SessionLocal, "test-heartbeat-isolation", deadline=None, batch_size=1)
    assert not result.errors, f"le worker a rencontré des erreurs : {result.errors}"
    assert result.done == 1

    assert _observed_visible_before_completion == [False], (
        "le renommage était visible depuis une connexion indépendante avant même la fin du "
        "handler : ctx.heartbeat() a committé le travail métier en cours (revue J2, 🔴 n°2)"
    )

    # Une fois le job réellement terminé (`_guarded_transition` commit le tout), le
    # changement est bien là — le correctif n'empêche pas le travail d'aboutir, il retarde
    # simplement le commit jusqu'à la fin réelle du handler.
    db_session.refresh(user)
    assert user.full_name == _RENAMED_VALUE
