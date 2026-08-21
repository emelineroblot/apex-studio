"""Séparation des pilotes par capacité d'exécution (`queue/capabilities.py`).

Depuis la préparation du déploiement, le même `drain()` tourne dans deux environnements
inégaux : la fonction Vercel n'embarque pas le moteur OCR (trop lourd pour le plafond de
250 Mo), le worker lancé depuis un poste l'a. Un pilote incapable doit **laisser** le job
en file, jamais le réclamer pour l'échouer — sans quoi trois tentatives suffisent à tuer
un `ocr_media` que le worker aurait très bien traité, et le média perd son rattachement
automatique en silence.

La capacité sondée ici (`PROBE_CAPABILITY`) n'existe dans aucun environnement : ces tests
mesurent le mécanisme, jamais ce qui est installé sur la machine qui les exécute.
"""

from __future__ import annotations

from sqlalchemy import select

from apex.db import SessionLocal
from apex.models.job import Job
from apex.queue.capabilities import OCR_ENGINE, available_capabilities
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, get_handler, handler, unservable_kinds
from apex.queue.runner import drain

PROBE_CAPABILITY = "test_probe_capability_never_installed"
GATED_KIND = "test_capability_gated_probe"
PLAIN_KIND = "test_capability_plain_probe"

_executions: list[int] = []


@handler(GATED_KIND, max_attempts=3, requires=(PROBE_CAPABILITY,))
def _gated_handler(ctx: JobContext) -> dict[str, bool]:
    _executions.append(ctx.job.id)
    return {"ok": True}


@handler(PLAIN_KIND, max_attempts=3)
def _plain_handler(ctx: JobContext) -> dict[str, bool]:
    return {"ok": True}


def _fetch(job_id: int) -> Job:
    session = SessionLocal()
    try:
        return session.execute(select(Job).where(Job.id == job_id)).scalars().one()
    finally:
        session.close()


def test_un_job_hors_capacite_reste_intact_et_compte_comme_differe(db_session) -> None:
    job_id = enqueue(db_session, GATED_KIND, {}, dedupe_key="capability:deferred")
    db_session.commit()

    result = drain(SessionLocal, "test-worker-sans-capacite")

    job = _fetch(job_id)
    assert job.status == "pending", "un job hors capacité ne doit jamais être réclamé"
    # Le cœur du correctif : ni tentative consommée, ni verrou posé, ni erreur inscrite.
    # Le job doit être indiscernable d'un job jamais vu par ce worker.
    assert job.attempts == 0
    assert job.locked_by is None
    assert job.last_error is None
    assert result.claimed == 0
    # Différé, donc visible — « jamais de rejet silencieux » vaut aussi pour la file.
    assert result.deferred == 1
    assert result.remaining >= 1, "`deferred` est un sous-ensemble de `remaining`"


def test_le_meme_job_est_traite_par_un_pilote_capable(db_session) -> None:
    job_id = enqueue(db_session, GATED_KIND, {}, dedupe_key="capability:served")
    db_session.commit()

    # `excluded_kinds=()` : simule le worker qui, lui, a la capacité — sans dépendre de
    # ce qui est réellement installé ici.
    result = drain(SessionLocal, "test-worker-capable", excluded_kinds=())

    assert result.done == 1
    assert result.deferred == 0
    assert _fetch(job_id).status == "done"
    assert job_id in _executions


def test_un_job_differe_en_tete_de_file_ne_bloque_pas_les_suivants(db_session) -> None:
    """`LIMIT` s'applique **après** le filtre : sinon un `ocr_media` prioritaire en tête
    consommerait le lot entier à chaque tick et gèlerait toute la file en ligne."""
    gated_id = enqueue(db_session, GATED_KIND, {}, dedupe_key="capability:head", priority=1)
    plain_id = enqueue(db_session, PLAIN_KIND, {}, dedupe_key="capability:tail", priority=50)
    db_session.commit()

    result = drain(SessionLocal, "test-worker-file-melangee", batch_size=1)

    assert result.done == 1
    assert _fetch(plain_id).status == "done"
    assert _fetch(gated_id).status == "pending"


def test_un_kind_inconnu_echoue_toujours_explicitement(db_session) -> None:
    """Non-régression §3-E.3 : le filtre est une **exclusion** des kinds connus et non
    servables, jamais une liste blanche — un kind inconnu doit rester réclamable pour
    échouer bruyamment, plutôt que de dormir en file sans que personne ne le remarque."""
    job_id = enqueue(db_session, "kind_jamais_enregistre", {}, dedupe_key="capability:unknown")
    db_session.commit()

    result = drain(SessionLocal, "test-worker-kind-inconnu")

    assert result.failed == 1
    job = _fetch(job_id)
    assert job.status == "failed"
    assert "kind de job inconnu" in (job.last_error or "")


def test_ocr_media_declare_le_moteur_et_lui_seul() -> None:
    spec = get_handler("ocr_media")
    assert spec is not None
    assert spec.requires == frozenset({OCR_ENGINE})

    sans_moteur = unservable_kinds(frozenset())
    assert "ocr_media" in sans_moteur
    # Aucun autre job métier ne doit dépendre du moteur : la re-projection des seuils
    # (`reclassify_ocr`) rejoue des candidats déjà stockés, sans jamais ré-inférer — c'est
    # ce qui la rend exécutable en ligne, et cette propriété mérite un test.
    assert "reclassify_ocr" not in sans_moteur
    assert "ingest_media" not in sans_moteur

    avec_moteur = unservable_kinds(frozenset({OCR_ENGINE}))
    assert "ocr_media" not in avec_moteur


def test_les_capacites_reelles_sont_un_sous_ensemble_des_capacites_connues() -> None:
    assert available_capabilities() <= frozenset({OCR_ENGINE})
