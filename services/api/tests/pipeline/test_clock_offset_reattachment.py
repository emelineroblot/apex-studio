"""Décalage d'horloge rétroactif (§3-F.3 du plan, critère d'acceptation J1) — un boîtier
réglé après coup doit **corriger** le rattachement de ses photos déjà ingérées, et le
recalcul ne doit **jamais dériver** si on règle le décalage plusieurs fois de suite.

`compute_shot_at` (`pipeline/exif.py`) recalcule toujours `shot_at` à partir de
`shot_at_exif` (brut, jamais modifié après l'ingestion) et du décalage **courant** — c'est
ce qui garantit l'absence de dérive cumulative. Ce test le prouve à l'échelle de l'API
réelle (`PATCH /cameras/{id}`), pas seulement sur la fonction pure : c'est le chemin que la
revue J1 a dû corriger deux fois (🔴 n°1, 🟠 « timezone seul ne déclenchait pas le
recalcul ») avant qu'il ne soit fiable.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from apex.db import SessionLocal
from apex.models.media import Media
from apex.queue.runner import drain
from tests.conftest import auth_headers, make_user
from tests.support.images import make_valid_jpeg

PARIS = ZoneInfo("Europe/Paris")


def _drain_queue() -> None:
    result = drain(SessionLocal, "test-clock-offset-worker", deadline=None)
    assert not result.errors, f"le worker a rencontré des erreurs : {result.errors}"


#: Marge volontaire (§ éviter un test aux bornes, sensible à la troncature à la seconde de
#: l'horodatage EXIF — celui-ci ne porte pas de microsecondes). Chaque étape de ce test
#: vise le **milieu** de la fenêtre, jamais une borne, pour rester robuste et non flaky.
INITIAL_LAG_MINUTES = 100
FIRST_OFFSET_SECONDS = 105 * 60  # ramène la photo à starts_at + 5 min (nettement dans la fenêtre)
SECOND_OFFSET_SECONDS = FIRST_OFFSET_SECONDS + 3600  # +1h de plus : starts_at + 65 min


def _setup_shooting_and_media(client: TestClient, db_session):
    """Shooting dont la fenêtre commence à `now` (UTC) ; une photo dont l'horodatage EXIF,
    interprété au fuseau par défaut du boîtier (Europe/Paris, décalage nul), tombe
    `INITIAL_LAG_MINUTES` minutes **avant** l'ouverture — donc hors fenêtre tant que le
    décalage n'est pas réglé.
    """
    owner = make_user(db_session, role="owner", email="owner-clockoffset@apex-test.dev")
    headers = auth_headers(owner)

    circuit = client.post(
        "/api/v1/circuits", json={"name": "Circuit Décalage Horloge"}, headers=headers
    ).json()

    starts_at = datetime.datetime.now(datetime.UTC)
    ends_at = starts_at + datetime.timedelta(hours=2)
    shooting = client.post(
        "/api/v1/shootings",
        json={
            "circuit_id": circuit["id"],
            "title": "Shooting décalage horloge",
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
        headers=headers,
    ).json()

    # Horodatage EXIF brut : `INITIAL_LAG_MINUTES` avant l'ouverture, exprimé comme le
    # lirait le boîtier (naïf). Interprété au fuseau par défaut (Europe/Paris) avec un
    # décalage nul, il tombe strictement avant `starts_at`.
    exif_naive = (
        (starts_at - datetime.timedelta(minutes=INITIAL_LAG_MINUTES))
        .astimezone(PARIS)
        .replace(tzinfo=None)
    )
    content = make_valid_jpeg(shot_at=exif_naive.strftime("%Y:%m:%d %H:%M:%S"), serial="CAM-DRIFT")

    batch = client.post(
        "/api/v1/batches",
        json={"expected_count": 1, "shooting_hint_id": shooting["id"]},
        headers=headers,
    ).json()
    resp = client.post(
        f"/api/v1/batches/{batch['id']}/files",
        headers={**headers, "Idempotency-Key": "clock-offset-1"},
        files={"file": ("clock.jpg", content, "image/jpeg")},
    )
    assert resp.status_code == 201, resp.text
    client.post(f"/api/v1/batches/{batch['id']}/close", headers=headers)
    _drain_queue()

    return owner, headers, shooting, resp.json()["media_id"]


def _media_shot_at(db_session, media_id: int) -> datetime.datetime:
    db_session.expire_all()
    media = db_session.get(Media, media_id)
    assert media is not None
    return media.shot_at


class TestClockOffsetRetroactiveCorrection:
    def test_offset_reattaches_photo_out_of_window(self, client: TestClient, db_session) -> None:
        _owner, headers, shooting, media_id = _setup_shooting_and_media(client, db_session)

        # Avant réglage : la photo est hors fenêtre, dans le bac « à rattacher ».
        media_before = db_session.get(Media, media_id)
        assert media_before.attachment_status == "unattached"
        assert media_before.attachment_detail == {"reason": "no_matching_window"}
        camera_id = media_before.camera_id
        assert camera_id is not None

        # Règle le décalage pour ramener la photo nettement à l'intérieur de la fenêtre
        # (starts_at + 5 min), loin des deux bornes.
        resp = client.patch(
            f"/api/v1/cameras/{camera_id}",
            json={"clock_offset_seconds": FIRST_OFFSET_SECONDS},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reattach_job_id"] is not None
        assert body["reattached"] == 1, "la photo hors fenêtre aurait dû être re-rattachée"

        media_after = db_session.get(Media, media_id)
        db_session.refresh(media_after)
        assert media_after.attachment_status == "shooting_attached"
        assert media_after.shooting_id == shooting["id"]

    def test_two_successive_offset_changes_do_not_drift(
        self, client: TestClient, db_session
    ) -> None:
        """Cœur du critère d'acceptation : régler le décalage **deux fois** ne doit jamais
        cumuler un delta sur `shot_at` — `compute_shot_at` repart toujours de
        `shot_at_exif` (brut, jamais réécrit), pas de la valeur déjà en base.
        """
        _owner, headers, _shooting, media_id = _setup_shooting_and_media(client, db_session)
        media_before = db_session.get(Media, media_id)
        camera_id = media_before.camera_id
        shot_at_exif = media_before.shot_at_exif
        assert shot_at_exif is not None

        # Premier réglage : ramène la photo à starts_at + 5 min.
        resp1 = client.patch(
            f"/api/v1/cameras/{camera_id}",
            json={"clock_offset_seconds": FIRST_OFFSET_SECONDS},
            headers=headers,
        )
        assert resp1.status_code == 200, resp1.text
        shot_at_after_first = _media_shot_at(db_session, media_id)

        # Deuxième réglage : une heure de plus que le premier (starts_at + 65 min).
        resp2 = client.patch(
            f"/api/v1/cameras/{camera_id}",
            json={"clock_offset_seconds": SECOND_OFFSET_SECONDS},
            headers=headers,
        )
        assert resp2.status_code == 200, resp2.text
        shot_at_after_second = _media_shot_at(db_session, media_id)

        delta = (shot_at_after_second - shot_at_after_first).total_seconds()
        expected_delta = SECOND_OFFSET_SECONDS - FIRST_OFFSET_SECONDS
        assert delta == expected_delta, (
            f"le delta entre les deux réglages doit être exactement {expected_delta}s ; "
            f"obtenu {delta}s — une dérive indique que le recalcul part de la valeur déjà "
            "en base plutôt que de l'EXIF brut"
        )

        # Revenir au premier réglage doit reproduire EXACTEMENT le même `shot_at` qu'après
        # le premier réglage — aucune dérive cumulée par les recalculs intermédiaires.
        resp3 = client.patch(
            f"/api/v1/cameras/{camera_id}",
            json={"clock_offset_seconds": FIRST_OFFSET_SECONDS},
            headers=headers,
        )
        assert resp3.status_code == 200, resp3.text
        shot_at_after_reset = _media_shot_at(db_session, media_id)

        assert shot_at_after_reset == shot_at_after_first, (
            "revenir au décalage initial doit reproduire bit-à-bit le shot_at initial : "
            f"{shot_at_after_reset!r} != {shot_at_after_first!r} (dérive cumulative détectée)"
        )

        # Et les deux valeurs sont bien dérivées de l'EXIF brut, jamais modifié.
        media_final = db_session.get(Media, media_id)
        db_session.refresh(media_final)
        assert media_final.shot_at_exif == shot_at_exif
