"""Pipeline de bout en bout (§3-F du plan) — sur de **vraies images** (`tests/support/images.py`),
via l'API réelle (upload) et le worker réel (`drain()`), aucun mock (§5 du plan).

Couvre les critères d'acceptation J1 : EXIF/rattachement temporel, dédoublonnage exact,
regroupement de rafales, quarantaine motivée pour fichier tronqué / dimensions aberrantes /
non-image, et idempotence de l'upload.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from apex.db import SessionLocal
from apex.models.media import Media, MediaSeries
from apex.queue.runner import drain
from tests.conftest import auth_headers, make_user
from tests.support.images import (
    make_burst_frame,
    make_no_exif_jpeg,
    make_not_an_image,
    make_truncated_jpeg,
    make_undersized_jpeg,
    make_valid_jpeg,
)

PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture
def shooting_ctx(client: TestClient, db_session):
    owner = make_user(db_session, role="owner", email="owner-pipeline@apex-test.dev")
    headers = auth_headers(owner)

    circuit = client.post(
        "/api/v1/circuits", json={"name": "Circuit Pipeline Test"}, headers=headers
    ).json()

    now = datetime.datetime.now(datetime.UTC)
    starts_at = now
    ends_at = now + datetime.timedelta(hours=6)
    shooting = client.post(
        "/api/v1/shootings",
        json={
            "circuit_id": circuit["id"],
            "title": "Shooting pipeline test",
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
        headers=headers,
    ).json()

    midpoint_utc = starts_at + (ends_at - starts_at) / 2
    midpoint_paris = midpoint_utc.astimezone(PARIS).replace(tzinfo=None)

    return {
        "owner": owner,
        "headers": headers,
        "shooting": shooting,
        "midpoint_paris": midpoint_paris,
    }


def _upload_and_close(
    client: TestClient, headers: dict, shooting_id: int, files: dict[str, bytes]
) -> int:
    batch = client.post(
        "/api/v1/batches",
        json={"expected_count": len(files), "shooting_hint_id": shooting_id},
        headers=headers,
    ).json()
    batch_id = batch["id"]
    for key, content in files.items():
        resp = client.post(
            f"/api/v1/batches/{batch_id}/files",
            headers={**headers, "Idempotency-Key": key},
            files={"file": (f"{key}.jpg", content, "image/jpeg")},
        )
        assert resp.status_code in (200, 201, 413), resp.text
    client.post(f"/api/v1/batches/{batch_id}/close", headers=headers)
    return batch_id


def _drain_queue() -> None:
    result = drain(SessionLocal, "test-worker", deadline=None)
    assert not result.errors, f"le worker a rencontré des erreurs : {result.errors}"


def _media_by_key(db_session, batch_id: int, idempotency_key: str) -> Media:
    from sqlalchemy import select

    media = db_session.execute(
        select(Media).where(Media.batch_id == batch_id, Media.idempotency_key == idempotency_key)
    ).scalar_one()
    db_session.refresh(media)
    return media


class TestValidImage:
    def test_ingested_and_attached_by_time_window(self, client, db_session, shooting_ctx):
        shot_at = shooting_ctx["midpoint_paris"].strftime("%Y:%m:%d %H:%M:%S")
        content = make_valid_jpeg(shot_at=shot_at)
        batch_id = _upload_and_close(
            client, shooting_ctx["headers"], shooting_ctx["shooting"]["id"], {"valid-1": content}
        )
        _drain_queue()

        media = _media_by_key(db_session, batch_id, "valid-1")
        assert media.ingest_status == "ingested"
        assert media.attachment_status == "shooting_attached"
        assert media.shooting_id == shooting_ctx["shooting"]["id"]
        assert media.shot_at is not None
        assert media.content_hash is not None
        assert media.storage_key_hd and media.storage_key_preview and media.storage_key_thumb
        assert media.phash is not None


class TestQuarantine:
    @pytest.mark.parametrize(
        ("builder", "expected_reason"),
        [
            (make_truncated_jpeg, "truncated_file"),
            (make_undersized_jpeg, "dimensions_out_of_range"),
            (make_not_an_image, "not_an_image"),
        ],
    )
    def test_bad_file_is_quarantined_with_readable_reason(
        self, client, db_session, shooting_ctx, builder, expected_reason
    ):
        content = builder()
        batch_id = _upload_and_close(
            client, shooting_ctx["headers"], shooting_ctx["shooting"]["id"], {"bad-1": content}
        )
        _drain_queue()

        media = _media_by_key(db_session, batch_id, "bad-1")
        assert media.ingest_status == "quarantined"
        assert media.quarantine_reason == expected_reason
        # `quarantine_reason` porte le motif lisible (traduit côté front) ; `detail` reste
        # `{}` quand rien n'a pu être mesuré (ex. fichier illisible dès l'ouverture) — un
        # dict jamais `NULL`, pas nécessairement non vide.
        assert media.quarantine_detail is not None


class TestNoExif:
    def test_no_exif_lands_in_unattached_bin(self, client, db_session, shooting_ctx):
        content = make_no_exif_jpeg()
        batch_id = _upload_and_close(
            client, shooting_ctx["headers"], shooting_ctx["shooting"]["id"], {"no-exif-1": content}
        )
        _drain_queue()

        media = _media_by_key(db_session, batch_id, "no-exif-1")
        # Jamais perdue : ingérée avec succès, seulement pas rattachée.
        assert media.ingest_status == "ingested"
        assert media.attachment_status == "unattached"
        assert media.attachment_detail == {"reason": "no_exif_timestamp"}


class TestDuplicate:
    def test_exact_duplicate_points_to_master(self, client, db_session, shooting_ctx):
        shot_at = shooting_ctx["midpoint_paris"].strftime("%Y:%m:%d %H:%M:%S")
        content = make_valid_jpeg(shot_at=shot_at)
        batch_id = _upload_and_close(
            client,
            shooting_ctx["headers"],
            shooting_ctx["shooting"]["id"],
            {"dup-master": content, "dup-copy": content},
        )
        _drain_queue()

        master = _media_by_key(db_session, batch_id, "dup-master")
        duplicate = _media_by_key(db_session, batch_id, "dup-copy")
        assert master.duplicate_of_media_id is None
        assert duplicate.duplicate_of_media_id == master.id
        assert duplicate.storage_key_hd == master.storage_key_hd  # un seul objet HD


class TestBurstSeries:
    def test_burst_is_grouped_with_sharpest_representative(self, client, db_session, shooting_ctx):
        base = shooting_ctx["midpoint_paris"]
        files = {
            f"burst-{i}": make_burst_frame(
                i, shot_at=base + datetime.timedelta(milliseconds=300 * i)
            )
            for i in range(5)
        }
        batch_id = _upload_and_close(
            client, shooting_ctx["headers"], shooting_ctx["shooting"]["id"], files
        )
        _drain_queue()

        medias = [_media_by_key(db_session, batch_id, key) for key in files]
        for m in medias:
            assert m.ingest_status == "ingested"
            assert m.attachment_status == "shooting_attached"

        grouped = [m for m in medias if m.series_id is not None]
        assert len(grouped) >= 2, "au moins une partie de la rafale doit former une série"

        series = db_session.get(MediaSeries, grouped[0].series_id)
        assert series is not None
        assert series.member_count == len(grouped)

        representatives = [m for m in grouped if m.is_series_representative]
        assert len(representatives) == 1
        representative = representatives[0]
        others = [m for m in grouped if m.id != representative.id]
        assert all((representative.sharpness or 0) >= (m.sharpness or 0) for m in others)


class TestUploadIdempotency:
    def test_replaying_the_same_idempotency_key_does_not_duplicate(self, client, shooting_ctx):
        content = make_valid_jpeg()
        headers = shooting_ctx["headers"]
        shooting_id = shooting_ctx["shooting"]["id"]

        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 1, "shooting_hint_id": shooting_id},
            headers=headers,
        ).json()

        first = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "replay-key"},
            files={"file": ("a.jpg", content, "image/jpeg")},
        )
        assert first.status_code == 201
        assert first.json()["duplicate"] is False

        second = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "replay-key"},
            files={"file": ("a.jpg", content, "image/jpeg")},
        )
        assert second.status_code == 200
        assert second.json()["duplicate"] is True
        assert second.json()["media_id"] == first.json()["media_id"]
