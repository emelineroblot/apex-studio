"""Reprise après crash (§3-E.5 du plan) — un job `running` sans heartbeat récent est repris
par `reap_stale` : `pending` s'il reste des tentatives, `dead` sinon. Un `ingest_media` mort
**doit** quarantiner son média (`on_dead`, jamais un état intermédiaire indéfini).
"""

from __future__ import annotations

import datetime

from apex.models.job import Job
from apex.models.media import Media, UploadBatch
from apex.models.user import AppUser
from apex.queue.claim import reap_stale
from apex.queue.enqueue import enqueue

STALE_HEARTBEAT = datetime.timedelta(minutes=10)


def _make_uploaded_media(db_session) -> Media:
    user = AppUser(
        email="crash-owner@apex-test.dev",
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
        idempotency_key="crash-test",
        original_filename="crash.jpg",
        byte_size=123,
        ingest_status="uploaded",
        attachment_status="unattached",
    )
    db_session.add(media)
    db_session.flush()
    db_session.commit()
    return media


def test_stale_running_job_with_attempts_left_goes_back_to_pending(db_session) -> None:
    media = _make_uploaded_media(db_session)
    job_id = enqueue(
        db_session, "ingest_media", {"media_id": media.id}, dedupe_key=f"media:{media.id}"
    )
    db_session.commit()

    job = db_session.get(Job, job_id)
    job.status = "running"
    job.attempts = 1
    job.max_attempts = 3
    job.heartbeat_at = datetime.datetime.now(datetime.UTC) - STALE_HEARTBEAT
    db_session.commit()

    reaped = reap_stale(db_session, stale_after=datetime.timedelta(minutes=3))
    assert reaped == 1

    db_session.refresh(job)
    assert job.status == "pending"
    assert "repris après worker silencieux" in (job.last_error or "")

    db_session.refresh(media)
    assert media.ingest_status == "uploaded"  # inchangé : encore des tentatives possibles


def test_stale_running_job_exhausted_goes_dead_and_quarantines_media(db_session) -> None:
    media = _make_uploaded_media(db_session)
    job_id = enqueue(
        db_session, "ingest_media", {"media_id": media.id}, dedupe_key=f"media:{media.id}"
    )
    db_session.commit()

    job = db_session.get(Job, job_id)
    job.status = "running"
    job.attempts = 3
    job.max_attempts = 3
    job.heartbeat_at = datetime.datetime.now(datetime.UTC) - STALE_HEARTBEAT
    job.last_error = "erreur simulée"
    db_session.commit()

    reaped = reap_stale(db_session, stale_after=datetime.timedelta(minutes=3))
    assert reaped == 1

    db_session.refresh(job)
    assert job.status == "dead"

    db_session.refresh(media)
    # §3-E.5 : « un passage à dead doit produire un effet métier lisible » — jamais un
    # média oublié en `uploaded`/`processing` pour toujours.
    assert media.ingest_status == "quarantined"
    assert media.quarantine_reason == "ingest_failed"
    assert media.quarantine_detail is not None
    assert media.quarantine_detail.get("reason") == "job_dead"


def test_kind_without_on_dead_hook_leaves_no_orphan_but_no_crash(db_session) -> None:
    """Un `kind` mort sans `on_dead` enregistré ne doit jamais faire planter `reap_stale`."""
    job_id = enqueue(db_session, "sweep_orphans", {}, dedupe_key="sweep-crash-test")
    db_session.commit()

    job = db_session.get(Job, job_id)
    job.status = "running"
    job.attempts = 3
    job.max_attempts = 3
    job.heartbeat_at = datetime.datetime.now(datetime.UTC) - STALE_HEARTBEAT
    db_session.commit()

    reaped = reap_stale(db_session, stale_after=datetime.timedelta(minutes=3))
    assert reaped == 1

    # `SessionLocal` est configurée `expire_on_commit=False` (§ db.py) : l'UPDATE SQL brut
    # de `reap_stale` ne rafraîchit pas automatiquement l'objet ORM déjà chargé dans cette
    # même session — `refresh()` explicite requis, sinon on relit un attribut périmé.
    db_session.refresh(job)
    assert job.status == "dead"
