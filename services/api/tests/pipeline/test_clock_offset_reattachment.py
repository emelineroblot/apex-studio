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
from sqlalchemy import select

from apex.db import SessionLocal
from apex.models.media import Media
from apex.queue.runner import drain
from tests.conftest import auth_headers, make_user
from tests.support.images import make_burst_frame, make_valid_jpeg

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


def _media_by_idempotency_key(db_session, batch_id: int, idempotency_key: str) -> Media:
    db_session.expire_all()
    media = db_session.execute(
        select(Media).where(Media.batch_id == batch_id, Media.idempotency_key == idempotency_key)
    ).scalar_one()
    db_session.refresh(media)
    return media


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


class TestClockOffsetWithGroupedBurst:
    """Revue J1 (🔴, bloquant) — le trou identifié en revue : les deux tests ci-dessus ne
    touchent jamais aux séries. `attach_media_by_time` (`pipeline/attach_time.py`) ne
    modifie jamais `series_id`/`is_series_representative`, et l'ancien `reattach_camera`
    ne rejouait jamais le regroupement des rafales après un rattachement — une rafale déjà
    groupée qui sort de sa fenêtre après un décalage d'horloge laissait ses membres non
    représentants invisibles à la fois dans l'onglet « Tout » (`series=collapsed`, le
    défaut) et dans le bac « à rattacher » (`unattached=true`, même filtre), sans qu'aucune
    trace n'indique à l'utilisateur que ces photos existent encore.
    """

    def test_reattach_does_not_drop_series_members_when_burst_leaves_window(
        self, client: TestClient, db_session
    ) -> None:
        owner = make_user(db_session, role="owner", email="owner-burstoffset@apex-test.dev")
        headers = auth_headers(owner)

        circuit = client.post(
            "/api/v1/circuits", json={"name": "Circuit Rafale + Décalage"}, headers=headers
        ).json()

        starts_at = datetime.datetime.now(datetime.UTC)
        ends_at = starts_at + datetime.timedelta(hours=2)
        shooting = client.post(
            "/api/v1/shootings",
            json={
                "circuit_id": circuit["id"],
                "title": "Shooting rafale + décalage",
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            },
            headers=headers,
        ).json()

        midpoint_utc = starts_at + (ends_at - starts_at) / 2
        midpoint_paris = midpoint_utc.astimezone(PARIS).replace(tzinfo=None)

        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 3, "shooting_hint_id": shooting["id"]},
            headers=headers,
        ).json()
        files = {
            f"burst-{i}": make_burst_frame(
                i,
                shot_at=midpoint_paris + datetime.timedelta(milliseconds=300 * i),
                serial="CAM-BURST-DRIFT",
            )
            for i in range(3)
        }
        for key, content in files.items():
            resp = client.post(
                f"/api/v1/batches/{batch['id']}/files",
                headers={**headers, "Idempotency-Key": key},
                files={"file": (f"{key}.jpg", content, "image/jpeg")},
            )
            assert resp.status_code == 201, resp.text
        client.post(f"/api/v1/batches/{batch['id']}/close", headers=headers)
        _drain_queue()

        media_ids = list(
            db_session.execute(
                select(Media.id).where(Media.batch_id == batch["id"]).order_by(Media.id)
            ).scalars()
        )
        assert len(media_ids) == 3

        db_session.expire_all()
        medias_before = [db_session.get(Media, mid) for mid in media_ids]
        for m in medias_before:
            assert m.attachment_status == "shooting_attached"
        grouped_before = [m for m in medias_before if m.series_id is not None]
        assert len(grouped_before) >= 2, "la rafale doit être groupée en série avant le décalage"
        camera_id = medias_before[0].camera_id
        assert camera_id is not None
        assert all(m.camera_id == camera_id for m in medias_before)

        # Décalage massif (+5 jours) : sort toute la rafale de la fenêtre du shooting —
        # reproduction du scénario de la revue.
        resp = client.patch(
            f"/api/v1/cameras/{camera_id}",
            json={"clock_offset_seconds": 5 * 24 * 3600},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["reattached"] == 3

        db_session.expire_all()
        medias_after = [db_session.get(Media, mid) for mid in media_ids]
        for m in medias_after:
            assert m.attachment_status == "unattached", (
                "toute la rafale doit sortir de la fenêtre après le décalage"
            )
            assert m.shooting_id is None
            assert m.series_id is None, (
                "un média sans shooting ne peut plus appartenir à une série (correctif 🔴)"
            )
            assert m.is_series_representative is False

        default_page = client.get(
            "/api/v1/media", params={"batch_id": batch["id"]}, headers=headers
        ).json()
        default_ids = {item["id"] for item in default_page["items"]}
        assert default_ids == set(media_ids), (
            "aucun média ne doit disparaître de l'onglet « Tout » (défaut, `series=collapsed`) "
            "après le décalage"
        )

        unattached_page = client.get(
            "/api/v1/media",
            params={"batch_id": batch["id"], "unattached": True},
            headers=headers,
        ).json()
        unattached_ids = {item["id"] for item in unattached_page["items"]}
        assert unattached_ids == set(media_ids), (
            "aucun média ne doit disparaître du bac « à rattacher » après le décalage"
        )


class TestClockOffsetSeriesBoundaryCrossing:
    """Cas voisin soupçonné en revue, sans avoir été reproduit : après recalage, le
    représentant d'une rafale atterrit dans un nouveau shooting (B) tandis qu'un autre
    membre reste tout juste hors fenêtre (`unattached`). Construit sur la borne exacte de
    `Shooting.period` (colonne générée `tstzrange(starts_at, ends_at, '[)')`,
    `models/shooting.py`) pour séparer déterministiquement les deux membres d'une seule
    seconde, sans marge hasardeuse.
    """

    def test_burst_split_across_shooting_boundary_after_offset_keeps_both_members_visible(
        self, client: TestClient, db_session
    ) -> None:
        owner = make_user(db_session, role="owner", email="owner-burstboundary@apex-test.dev")
        headers = auth_headers(owner)

        circuit = client.post(
            "/api/v1/circuits", json={"name": "Circuit Rafale Bordure"}, headers=headers
        ).json()

        # `microsecond=0` : `shot_at_exif` n'a qu'une résolution de la seconde (EXIF,
        # `%Y:%m:%d %H:%M:%S`) — sans cette troncature, les bornes `starts_at`/`ends_at`
        # (microseconde réelle de `now()`) et les `shot_at` recalculés (toujours à la
        # microseconde nulle) ne s'alignent jamais exactement, et la construction à la
        # seconde près ci-dessous rate son coup silencieusement.
        a_starts_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
        a_ends_at = a_starts_at + datetime.timedelta(hours=2)
        shooting_a = client.post(
            "/api/v1/shootings",
            json={
                "circuit_id": circuit["id"],
                "title": "Shooting A",
                "starts_at": a_starts_at.isoformat(),
                "ends_at": a_ends_at.isoformat(),
            },
            headers=headers,
        ).json()

        # B démarre exactement 1 seconde après la fin de A : pas de chevauchement, pas
        # d'ambiguïté de fenêtre (`find_candidate_shootings` ne verra jamais les deux à la
        # fois pour un même instant).
        b_starts_at = a_ends_at + datetime.timedelta(seconds=1)
        b_ends_at = b_starts_at + datetime.timedelta(hours=2)
        shooting_b = client.post(
            "/api/v1/shootings",
            json={
                "circuit_id": circuit["id"],
                "title": "Shooting B",
                "starts_at": b_starts_at.isoformat(),
                "ends_at": b_ends_at.isoformat(),
            },
            headers=headers,
        ).json()

        # Horodatages choisis pour qu'un décalage de +100 s place :
        #   - frame0 pile sur `a_ends_at` (exclu de A par la borne `[)`) et 1 s avant
        #     `b_starts_at` -> hors fenêtre, `unattached` ;
        #   - frame1 (1 s plus tard dans la rafale d'origine) pile sur `b_starts_at`
        #     (inclus par `[)`) -> rattaché à B.
        t0_target = a_ends_at - datetime.timedelta(seconds=100)
        t1_target = t0_target + datetime.timedelta(seconds=1)
        frame0_shot_at = t0_target.astimezone(PARIS).replace(tzinfo=None)
        frame1_shot_at = t1_target.astimezone(PARIS).replace(tzinfo=None)

        batch = client.post(
            "/api/v1/batches",
            json={"expected_count": 2, "shooting_hint_id": shooting_a["id"]},
            headers=headers,
        ).json()
        content0 = make_burst_frame(0, shot_at=frame0_shot_at, serial="CAM-BOUNDARY")
        content1 = make_burst_frame(1, shot_at=frame1_shot_at, serial="CAM-BOUNDARY")
        for key, content in {"frame-0": content0, "frame-1": content1}.items():
            resp = client.post(
                f"/api/v1/batches/{batch['id']}/files",
                headers={**headers, "Idempotency-Key": key},
                files={"file": (f"{key}.jpg", content, "image/jpeg")},
            )
            assert resp.status_code == 201, resp.text
        client.post(f"/api/v1/batches/{batch['id']}/close", headers=headers)
        _drain_queue()

        media0 = _media_by_idempotency_key(db_session, batch["id"], "frame-0")
        media1 = _media_by_idempotency_key(db_session, batch["id"], "frame-1")
        assert media0.attachment_status == "shooting_attached"
        assert media0.shooting_id == shooting_a["id"]
        assert media1.attachment_status == "shooting_attached"
        assert media1.shooting_id == shooting_a["id"]
        camera_id = media0.camera_id
        assert camera_id is not None
        assert media1.camera_id == camera_id

        resp = client.patch(
            f"/api/v1/cameras/{camera_id}",
            json={"clock_offset_seconds": 100},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["reattached"] == 2

        media0_after = _media_by_idempotency_key(db_session, batch["id"], "frame-0")
        media1_after = _media_by_idempotency_key(db_session, batch["id"], "frame-1")

        assert media0_after.attachment_status == "unattached", (
            "frame0 doit tomber exactement dans le trou entre A (exclu, borne `[)`) et B"
        )
        assert media0_after.shooting_id is None
        assert media0_after.series_id is None
        assert media1_after.attachment_status == "shooting_attached"
        assert media1_after.shooting_id == shooting_b["id"], (
            "frame1 doit atterrir pile sur l'ouverture de B (borne incluse, `[)`)"
        )
        assert media1_after.series_id is None

        default_page = client.get(
            "/api/v1/media", params={"batch_id": batch["id"]}, headers=headers
        ).json()
        default_ids = {item["id"] for item in default_page["items"]}
        assert default_ids == {media0.id, media1.id}, (
            "le membre resté hors fenêtre ne doit pas disparaître alors que l'autre a "
            "rejoint un nouveau shooting"
        )

        unattached_page = client.get(
            "/api/v1/media",
            params={"batch_id": batch["id"], "unattached": True},
            headers=headers,
        ).json()
        unattached_ids = {item["id"] for item in unattached_page["items"]}
        assert unattached_ids == {media0.id}
