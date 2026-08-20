"""Preuve du correctif revue J1 (🔴 n°1) : un job mort par **épuisement des tentatives**
(chemin normal de `_process_one`, pas `reap_stale`) doit dispatcher `spec.on_dead`, exactement
comme le chemin `reap_stale` le fait déjà (couvert par `tests/queue/test_crash_recovery.py`).

Avant le correctif, `queue/runner.py` écrivait `status='dead'` sans jamais appeler
`on_dead` dans cette branche — un handler qui lève (y compris depuis du code hors de tout
`_step`, ex. `resolve_camera`/`compute_shot_at` avant leur propre correctif) laissait son
objet métier dans un état intermédiaire indéfiniment, hors de tout bac.
"""

from __future__ import annotations

from apex.db import SessionLocal
from apex.models.job import Job
from apex.models.media import Media, UploadBatch
from apex.models.user import AppUser
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, handler
from apex.queue.runner import drain

DEAD_KIND = "test_on_dead_dispatch_probe"


def _on_dead(session, job) -> None:  # noqa: ANN001 — signature imposée par `OnDeadFunc`
    media_id = job.payload.get("media_id")
    media = session.get(Media, media_id)
    if media is None:
        return
    media.ingest_status = "quarantined"
    media.quarantine_reason = "ingest_failed"
    media.quarantine_detail = {"reason": "job_dead", "last_error": job.last_error}
    media.attachment_status = "unattached"


@handler(DEAD_KIND, max_attempts=1, on_dead=_on_dead)
def _always_fails(ctx: JobContext) -> dict[str, bool]:
    # Simule un handler qui lève **hors** de tout `_step` — la cause exacte n'importe pas
    # pour ce test : le contrat à vérifier est « `on_dead` doit être dispatché, quelle que
    # soit l'étape qui a échoué ».
    raise RuntimeError("échec simulé hors de toute étape _step")


def _make_uploaded_media(db_session) -> Media:
    user = AppUser(
        email="on-dead-owner@apex-test.dev",
        password_hash="x",
        full_name="Owner",
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    batch = UploadBatch(created_by=user.id, expected_count=1, status="processing")
    db_session.add(batch)
    db_session.flush()
    media = Media(
        batch_id=batch.id,
        uploaded_by=user.id,
        idempotency_key="on-dead-test",
        original_filename="on-dead.jpg",
        byte_size=123,
        ingest_status="processing",
        attachment_status="unattached",
    )
    db_session.add(media)
    db_session.flush()
    db_session.commit()
    return media


def test_attempts_exhausted_dispatches_on_dead_and_quarantines_media(db_session) -> None:
    media = _make_uploaded_media(db_session)
    job_id = enqueue(
        db_session, DEAD_KIND, {"media_id": media.id}, dedupe_key=f"on-dead:{media.id}"
    )
    db_session.commit()

    # `max_attempts=1` : la première (et unique) tentative épuise directement le quota —
    # exerce la branche `_process_one` sans jamais passer par `reap_stale`.
    result = drain(SessionLocal, "test-on-dead-worker", deadline=None)

    assert result.dead == 1

    check_session = SessionLocal()
    try:
        job = check_session.get(Job, job_id)
        assert job is not None
        assert job.status == "dead"

        refreshed_media = check_session.get(Media, media.id)
        assert refreshed_media is not None
        # « Aucun job mort ne laisse un objet métier dans un état intermédiaire » (§3-E.5) :
        # le média doit atterrir dans un bac motivé, jamais rester `processing`.
        assert refreshed_media.ingest_status == "quarantined"
        assert refreshed_media.quarantine_reason == "ingest_failed"
        assert refreshed_media.quarantine_detail is not None
        assert refreshed_media.quarantine_detail.get("reason") == "job_dead"
        assert "échec simulé" in (refreshed_media.quarantine_detail.get("last_error") or "")
    finally:
        check_session.close()
