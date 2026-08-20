"""Couverture complémentaire des critères d'acceptation J1 :

- Quarantaine motivée pour les deux motifs *non* liés à l'intégrité du fichier
  (`quota_exceeded`, `too_large`) — jamais un rejet muet (§3-H.3) — et pour l'incohérence
  EXIF (`exif_inconsistent`, §3-F.2), qui n'avait aucun test avant ce lot.
- « Une rafale est regroupée en série et n'affiche qu'un représentant » et « deux fichiers
  identiques sont dédoublonnés » **à l'échelle de la liste `GET /media`**, pas seulement en
  base — c'est cette surface-là que consomme la grille du frontend, et c'est là que la
  passe d'intégration live a trouvé une régression (`series_id`/`is_series_representative`
  absents de `MediaSummary`, §5 du plan).
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apex.config import settings
from apex.db import SessionLocal
from apex.models.media import Media
from apex.models.shooting import Shooting
from apex.queue.runner import drain
from tests.conftest import auth_headers, make_user
from tests.support.images import make_burst_frame, make_valid_jpeg


def _drain_queue() -> None:
    result = drain(SessionLocal, "test-quarantine-listing-worker", deadline=None)
    assert not result.errors, f"le worker a rencontré des erreurs : {result.errors}"


@pytest.fixture
def shooting_ctx(client: TestClient, db_session):
    owner = make_user(db_session, role="owner", email="owner-qlist@apex-test.dev")
    headers = auth_headers(owner)
    circuit = client.post(
        "/api/v1/circuits", json={"name": "Circuit Quarantaine/Listing"}, headers=headers
    ).json()
    now = datetime.datetime.now(datetime.UTC)
    shooting = client.post(
        "/api/v1/shootings",
        json={
            "circuit_id": circuit["id"],
            "title": "Shooting quarantaine/listing",
            "starts_at": now.isoformat(),
            "ends_at": (now + datetime.timedelta(hours=6)).isoformat(),
        },
        headers=headers,
    ).json()
    return {"owner": owner, "headers": headers, "shooting": shooting}


class TestQuotaAndSizeQuarantine:
    def test_file_over_shooting_quota_is_created_and_quarantined_not_silently_rejected(
        self, client: TestClient, db_session, shooting_ctx
    ) -> None:
        shooting_id = shooting_ctx["shooting"]["id"]
        # Quota artificiellement minuscule : n'importe quel JPEG de test le dépasse.
        shooting_row = db_session.get(Shooting, shooting_id)
        assert shooting_row is not None
        shooting_row.quota_bytes = 10
        db_session.commit()

        headers = shooting_ctx["headers"]
        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 1, "shooting_hint_id": shooting_id},
            headers=headers,
        ).json()
        content = make_valid_jpeg()
        resp = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "quota-1"},
            files={"file": ("quota.jpg", content, "image/jpeg")},
        )
        # Jamais un rejet muet (§3-H.3) : 413 avec le média créé et son id dans le détail.
        assert resp.status_code == 413
        body = resp.json()
        assert body["code"] == "quota_exceeded"
        media_id = body["detail"]["media_id"]
        assert media_id is not None

        media = db_session.get(Media, media_id)
        db_session.refresh(media)
        assert media.ingest_status == "quarantined"
        assert media.quarantine_reason == "quota_exceeded"
        assert media.quarantine_detail is not None
        assert "quota_bytes" in media.quarantine_detail

    def test_file_over_max_upload_bytes_is_created_and_quarantined_not_silently_rejected(
        self, client: TestClient, db_session, shooting_ctx, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "max_upload_bytes", 100)
        headers = shooting_ctx["headers"]
        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 1, "shooting_hint_id": shooting_ctx["shooting"]["id"]},
            headers=headers,
        ).json()
        content = make_valid_jpeg()
        assert len(content) > 100
        resp = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "toolarge-1"},
            files={"file": ("big.jpg", content, "image/jpeg")},
        )
        assert resp.status_code == 413
        body = resp.json()
        assert body["code"] == "file_too_large"
        media_id = body["detail"]["media_id"]

        media = db_session.get(Media, media_id)
        db_session.refresh(media)
        assert media.ingest_status == "quarantined"
        assert media.quarantine_reason == "too_large"


class TestExifInconsistentQuarantine:
    def test_shot_at_before_year_2000_is_quarantined_with_readable_reason(
        self, client: TestClient, db_session, shooting_ctx
    ) -> None:
        content = make_valid_jpeg(shot_at="1998:01:01 10:00:00")
        headers = shooting_ctx["headers"]
        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 1, "shooting_hint_id": shooting_ctx["shooting"]["id"]},
            headers=headers,
        ).json()
        resp = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "exif-1998"},
            files={"file": ("old.jpg", content, "image/jpeg")},
        )
        assert resp.status_code == 201
        _drain_queue()

        media = db_session.get(Media, resp.json()["media_id"])
        db_session.refresh(media)
        assert media.ingest_status == "quarantined"
        assert media.quarantine_reason == "exif_inconsistent"
        assert media.quarantine_detail is not None
        assert "shot_at_exif" in media.quarantine_detail

    def test_shot_at_far_in_the_future_is_quarantined_with_readable_reason(
        self, client: TestClient, db_session, shooting_ctx
    ) -> None:
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365 * 5)
        content = make_valid_jpeg(shot_at=future.strftime("%Y:%m:%d %H:%M:%S"))
        headers = shooting_ctx["headers"]
        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 1, "shooting_hint_id": shooting_ctx["shooting"]["id"]},
            headers=headers,
        ).json()
        resp = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "exif-future"},
            files={"file": ("future.jpg", content, "image/jpeg")},
        )
        assert resp.status_code == 201
        _drain_queue()

        media = db_session.get(Media, resp.json()["media_id"])
        db_session.refresh(media)
        assert media.ingest_status == "quarantined"
        assert media.quarantine_reason == "exif_inconsistent"


class TestListingCollapsesSeriesAndExcludesDuplicates:
    """§3-G : « une rafale est regroupée en série et n'affiche qu'un représentant » — vérifié
    ici sur la surface réellement consommée par la grille (`GET /media`), pas seulement en
    base. Le regroupement par hash perceptuel ne garantit pas de capturer 100% d'une rafale
    (seuil de distance de Hamming, comme le reconnaît déjà
    `tests/pipeline/test_ingest_e2e.py::TestBurstSeries`, qui tolère `len(grouped) >= 2`) —
    ce test suit la même tolérance, mais vérifie en plus que la liste par défaut
    (`series=collapsed`) n'affiche que les membres **non groupés** et le **représentant**
    de chaque série effectivement formée, jamais un membre secondaire.
    """

    def test_default_list_shows_only_one_item_per_burst_series(
        self, client: TestClient, db_session, shooting_ctx
    ) -> None:
        headers = shooting_ctx["headers"]
        shooting_id = shooting_ctx["shooting"]["id"]
        # Base de la rafale : 2 s après l'ouverture du shooting, jamais à la borne — évite
        # qu'une troncature à la seconde de l'horodatage EXIF (pas de microsecondes) ne
        # fasse tomber un cliché juste avant `starts_at` (constaté en vérification :
        # `shot_at` tronqué à la seconde peut être antérieur de l'ordre de la milliseconde).
        starts_at = datetime.datetime.fromisoformat(shooting_ctx["shooting"]["starts_at"])
        base = (starts_at + datetime.timedelta(seconds=2)).astimezone().replace(tzinfo=None)
        files = {
            f"listing-burst-{i}": make_burst_frame(
                i, shot_at=base + datetime.timedelta(milliseconds=300 * i)
            )
            for i in range(5)
        }
        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": len(files), "shooting_hint_id": shooting_id},
            headers=headers,
        ).json()
        for key, content in files.items():
            resp = client.post(
                f"/api/v1/batches/{batch['id']}/files",
                headers={**headers, "Idempotency-Key": key},
                files={"file": (f"{key}.jpg", content, "image/jpeg")},
            )
            assert resp.status_code == 201, resp.text
        client.post(f"/api/v1/batches/{batch['id']}/close", headers=headers)
        _drain_queue()

        burst_media = [
            db_session.execute(
                select(Media).where(Media.batch_id == batch["id"], Media.idempotency_key == key)
            ).scalar_one()
            for key in files
        ]
        for m in burst_media:
            assert m.attachment_status == "shooting_attached", (
                f"média {m.id} hors fenêtre du shooting ({m.shot_at!r}) — la marge de "
                "sécurité de ce test doit être revue"
            )
        grouped = [m for m in burst_media if m.series_id is not None]
        assert len(grouped) >= 2, "au moins une partie de la rafale doit former une série"
        representative_ids = {m.id for m in grouped if m.is_series_representative}
        assert len(representative_ids) == 1
        ungrouped_ids = {m.id for m in burst_media if m.series_id is None}
        expected_visible_ids = ungrouped_ids | representative_ids

        listed = client.get(
            "/api/v1/media", params={"shooting_id": shooting_id, "limit": 100}, headers=headers
        ).json()["items"]
        listed_burst_ids = {
            item["id"] for item in listed if item["id"] in {m.id for m in burst_media}
        }

        assert listed_burst_ids == expected_visible_ids, (
            "GET /media (série par défaut = collapsed) doit afficher les membres non "
            "groupés tels quels et un seul représentant par série formée (critère "
            f"d'acceptation J1) ; attendu {expected_visible_ids}, obtenu {listed_burst_ids}"
        )

    def test_default_list_excludes_exact_duplicates(
        self, client: TestClient, db_session, shooting_ctx
    ) -> None:
        headers = shooting_ctx["headers"]
        shooting_id = shooting_ctx["shooting"]["id"]
        content = make_valid_jpeg(serial="CAM-DUP-LIST")
        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 2, "shooting_hint_id": shooting_id},
            headers=headers,
        ).json()
        for key in ("dup-list-master", "dup-list-copy"):
            resp = client.post(
                f"/api/v1/batches/{batch['id']}/files",
                headers={**headers, "Idempotency-Key": key},
                files={"file": (f"{key}.jpg", content, "image/jpeg")},
            )
            assert resp.status_code == 201, resp.text
        client.post(f"/api/v1/batches/{batch['id']}/close", headers=headers)
        _drain_queue()

        copy_media = db_session.execute(
            select(Media).where(
                Media.batch_id == batch["id"], Media.idempotency_key == "dup-list-copy"
            )
        ).scalar_one()
        assert copy_media.duplicate_of_media_id is not None

        listed = client.get(
            "/api/v1/media", params={"shooting_id": shooting_id, "limit": 100}, headers=headers
        ).json()["items"]
        assert copy_media.id not in [item["id"] for item in listed]
