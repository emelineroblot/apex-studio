"""`media_search` reste **toujours** à jour (§3-K) — point de sortie signalé par l'agent OCR
(« `reindex_media` n'est enqueué nulle part ») : ce fichier verrouille que la projection est
rafraîchie à chaque endroit où `attachment_status`/le rattachement change, sans passer par un
`apex.cli reindex` manuel entre l'action et l'assertion.

Couverture : ingestion (pipeline réel), rattachement/retrait manuel, arbitrage humain en file
de validation, recalage d'horloge (`reattach_camera`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import SessionLocal
from apex.models.catalog import Camera
from apex.models.search import MediaOcrCandidate, MediaSearch
from apex.pipeline.ocr.classify import RESOLUTION_REVIEW
from apex.queue.runner import drain
from apex.services.ocr_settings import ENGINE_VERSION_DEFAULT
from apex.services.search_projection import project_media_search
from tests.conftest import auth_headers, make_user
from tests.search.factories import (
    make_circuit,
    make_client,
    make_driver,
    make_engagement,
    make_media,
    make_shooting,
    make_team,
    make_upload_batch,
)
from tests.support.images import make_valid_jpeg

PARIS = ZoneInfo("Europe/Paris")


def _drain() -> None:
    result = drain(SessionLocal, "test-reindex-worker", deadline=None)
    assert not result.errors, f"le worker a rencontré des erreurs : {result.errors}"


def _search_row(db_session: Session, media_id: int) -> MediaSearch:
    """Lit la ligne fraîche depuis `media_search`.

    `db_session` (fixture, `expire_on_commit=False`, § `apex/db.py`) ne rafraîchit jamais
    ses objets déjà chargés tout seul — sans `expire_all()`, une deuxième lecture de la
    **même** ligne renverrait l'objet mis en cache dans l'identity map, masquant
    silencieusement le commit fait par la requête HTTP (une session distincte). Ce n'est
    pas la projection qui serait périmée ici, seulement la relecture du test.
    """
    db_session.expire_all()
    row = db_session.execute(
        select(MediaSearch).where(MediaSearch.media_id == media_id)
    ).scalar_one_or_none()
    assert row is not None, f"media_id={media_id} absent de media_search — projection périmée"
    return row


class TestReindexAfterIngestion:
    def test_a_freshly_ingested_media_is_immediately_findable(self, client, db_session) -> None:
        owner = make_user(db_session, role="owner", email="owner-reindex-ingest@apex-test.dev")
        headers = auth_headers(owner)
        circuit = client.post(
            "/api/v1/circuits", json={"name": "Circuit Réindexation Ingestion"}, headers=headers
        ).json()
        starts_at = datetime.now(UTC)
        shooting = client.post(
            "/api/v1/shootings",
            json={
                "circuit_id": circuit["id"],
                "title": "Shooting réindexation",
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(hours=2)).isoformat(),
            },
            headers=headers,
        ).json()
        # § pieges-projet (2026-08-20) : l'EXIF est naïf, interprété au fuseau du **boîtier**
        # (Europe/Paris par défaut), pas celui de la machine de test — sans cette conversion
        # explicite, `shot_at` recalculé tombe hors fenêtre et le média part en
        # `unattached`, pas `shooting_attached`.
        shot_at_paris = (starts_at + timedelta(minutes=30)).astimezone(PARIS).replace(tzinfo=None)
        content = make_valid_jpeg(
            shot_at=shot_at_paris.strftime("%Y:%m:%d %H:%M:%S"), serial="CAM-REINDEX"
        )

        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 1, "shooting_hint_id": shooting["id"]},
            headers=headers,
        ).json()
        upload = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "reindex-ingest-1"},
            files={"file": ("reindex.jpg", content, "image/jpeg")},
        )
        assert upload.status_code == 201, upload.text
        media_id = upload.json()["media_id"]
        client.post(f"/api/v1/batches/{batch['id']}/close", headers=headers)
        _drain()

        row = _search_row(db_session, media_id)
        assert row.attachment_status == "shooting_attached"
        assert row.shooting_id == shooting["id"]


class TestReindexAfterManualAttachmentChanges:
    def test_attaching_from_the_unattached_bin_refreshes_the_projection(
        self, client, db_session
    ) -> None:
        owner = make_user(db_session, role="owner", email="owner-reindex-attach@apex-test.dev")
        headers = auth_headers(owner)
        circuit = make_circuit(db_session, "Circuit Rattachement Manuel")
        demo_client = make_client(db_session, "Client Rattachement Manuel")
        shooting = make_shooting(
            db_session, client=demo_client, circuit=circuit, starts_at=datetime.now(UTC)
        )
        batch = make_upload_batch(db_session, user=owner)
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=None,
            shot_at=datetime.now(UTC),
            attachment_status="unattached",
        )
        db_session.commit()
        project_media_search(db_session, None)
        db_session.commit()

        assert _search_row(db_session, media.id).shooting_id is None

        resp = client.post(
            f"/api/v1/media/{media.id}/attach",
            json={"shooting_id": shooting.id},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        row = _search_row(db_session, media.id)
        assert row.shooting_id == shooting.id
        assert row.attachment_status == "shooting_attached"

    def test_adding_and_removing_a_manual_engagement_refreshes_the_projection(
        self, client, db_session
    ) -> None:
        owner = make_user(db_session, role="owner", email="owner-reindex-engagement@apex-test.dev")
        headers = auth_headers(owner)
        circuit = make_circuit(db_session, "Circuit Engagement Manuel")
        demo_client = make_client(db_session, "Client Engagement Manuel")
        team = make_team(db_session, "Écurie Manuelle", demo_client)
        shooting = make_shooting(
            db_session, client=demo_client, circuit=circuit, starts_at=datetime.now(UTC)
        )
        engagement = make_engagement(db_session, shooting=shooting, car_number="21", team=team)
        batch = make_upload_batch(db_session, user=owner)
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            shot_at=datetime.now(UTC),
            attachment_status="shooting_attached",
            attachment_source="pipeline_time",
        )
        db_session.commit()
        project_media_search(db_session, None)
        db_session.commit()

        assert _search_row(db_session, media.id).team_ids is None

        resp = client.post(
            f"/api/v1/media/{media.id}/engagements",
            json={"engagement_id": engagement.id},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        row = _search_row(db_session, media.id)
        assert row.attachment_status == "engagement_attached"
        assert row.team_ids == [team.id]

        resp = client.delete(
            f"/api/v1/media/{media.id}/engagements/{engagement.id}", headers=headers
        )
        assert resp.status_code == 204, resp.text
        row = _search_row(db_session, media.id)
        assert row.attachment_status == "shooting_attached"
        assert not row.team_ids


class TestReindexAfterHumanArbitration:
    def test_accepting_a_review_candidate_refreshes_the_projection(
        self, client, db_session
    ) -> None:
        owner = make_user(db_session, role="owner", email="owner-reindex-review@apex-test.dev")
        headers = auth_headers(owner)
        circuit = make_circuit(db_session, "Circuit Arbitrage Humain")
        demo_client = make_client(db_session, "Client Arbitrage Humain")
        team = make_team(db_session, "Écurie Arbitrage", demo_client)
        driver = make_driver(db_session, "Pilote Arbitrage")
        shooting = make_shooting(
            db_session, client=demo_client, circuit=circuit, starts_at=datetime.now(UTC)
        )
        engagement = make_engagement(
            db_session, shooting=shooting, car_number="33", team=team, driver=driver
        )
        batch = make_upload_batch(db_session, user=owner)
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            shot_at=datetime.now(UTC),
            attachment_status="pending_review",
        )
        candidate = MediaOcrCandidate(
            media_id=media.id,
            raw_text="33",
            normalized_number="33",
            confidence=0.6,
            bbox={"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.1},
            engine_version=ENGINE_VERSION_DEFAULT,
            resolution=RESOLUTION_REVIEW,
            engagement_id=engagement.id,
        )
        db_session.add(candidate)
        db_session.commit()
        project_media_search(db_session, None)
        db_session.commit()

        assert _search_row(db_session, media.id).attachment_status == "pending_review"

        resp = client.post(
            "/api/v1/review/decisions",
            json={"decisions": [{"candidate_id": candidate.id, "action": "accept"}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["applied"] == 1

        row = _search_row(db_session, media.id)
        assert row.attachment_status == "engagement_attached"
        assert row.team_ids == [team.id]


class TestReindexAfterClockOffset:
    def test_a_retroactive_clock_offset_moves_the_media_between_shootings_in_the_projection(
        self, client, db_session
    ) -> None:
        owner = make_user(db_session, role="owner", email="owner-reindex-clock@apex-test.dev")
        headers = auth_headers(owner)
        circuit = make_circuit(db_session, "Circuit Décalage Horloge Recherche")
        demo_client = make_client(db_session, "Client Décalage Horloge")
        base = datetime.now(UTC).replace(microsecond=0)
        shooting1 = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
        shooting2 = make_shooting(
            db_session, client=demo_client, circuit=circuit, starts_at=base + timedelta(hours=3)
        )
        camera = Camera(model="Boîtier Test", make="Test", timezone="UTC", clock_offset_seconds=0)
        db_session.add(camera)
        db_session.flush()

        shot_at_exif = (base + timedelta(minutes=30)).replace(tzinfo=None)
        batch = make_upload_batch(db_session, user=owner)
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting1,
            camera=camera,
            shot_at=base + timedelta(minutes=30),
            attachment_status="shooting_attached",
            attachment_source="pipeline_time",
        )
        media.shot_at_exif = shot_at_exif
        db_session.commit()
        project_media_search(db_session, None)
        db_session.commit()

        assert _search_row(db_session, media.id).shooting_id == shooting1.id

        resp = client.patch(
            f"/api/v1/cameras/{camera.id}",
            json={"clock_offset_seconds": 3 * 3600},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["reattached"] == 1

        row = _search_row(db_session, media.id)
        assert row.shooting_id == shooting2.id
        assert row.shot_at == base + timedelta(hours=3, minutes=30)


class TestReindexAfterThresholdReclassification:
    def test_lowering_the_high_threshold_promotes_a_candidate_and_refreshes_the_projection(
        self, client, db_session
    ) -> None:
        """`PUT /settings/ocr` re-projette **sans ré-inférence** (§3-J.4) — la projection de
        recherche doit suivre la redistribution, pas seulement `media.attachment_status`.
        """
        owner = make_user(db_session, role="owner", email="owner-reindex-reclassify@apex-test.dev")
        headers = auth_headers(owner)
        circuit = make_circuit(db_session, "Circuit Reclassement")
        demo_client = make_client(db_session, "Client Reclassement")
        team = make_team(db_session, "Écurie Reclassement", demo_client)
        shooting = make_shooting(
            db_session, client=demo_client, circuit=circuit, starts_at=datetime.now(UTC)
        )
        engagement = make_engagement(db_session, shooting=shooting, car_number="55", team=team)
        batch = make_upload_batch(db_session, user=owner)
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            shot_at=datetime.now(UTC),
            attachment_status="shooting_attached",
        )
        # Score sous le seuil haut par défaut (0.85) mais au-dessus d'un seuil abaissé —
        # candidat déjà persisté, comme le prescrit §3-J.4 (« ne relance jamais l'inférence »).
        candidate = MediaOcrCandidate(
            media_id=media.id,
            raw_text="55",
            normalized_number="55",
            confidence=0.70,
            bbox={"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.1},
            engine_version=ENGINE_VERSION_DEFAULT,
            resolution=RESOLUTION_REVIEW,
            engagement_id=engagement.id,
        )
        db_session.add(candidate)
        db_session.commit()
        project_media_search(db_session, None)
        db_session.commit()

        assert _search_row(db_session, media.id).attachment_status == "shooting_attached"

        resp = client.put("/api/v1/settings/ocr", json={"high": 0.65, "low": 0.30}, headers=headers)
        assert resp.status_code == 200, resp.text

        row = _search_row(db_session, media.id)
        assert row.attachment_status == "engagement_attached"
        assert row.team_ids == [team.id]
