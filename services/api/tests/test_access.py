"""Cloisonnement des rôles (§3-I du plan) — matrice `owner`/`photographer` et exhaustivité
de l'authentification sur les routes internes.
"""

from __future__ import annotations

import datetime

from fastapi.testclient import TestClient

from apex.models.catalog import Camera
from tests.conftest import auth_headers, make_user

# Routes publiques listées par le plan (§3-I) — seules à échapper au sweep d'auth.
PUBLIC_PATHS = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/demo/accounts"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/jobs/tick"),  # secret partagé, pas un JWT (§3-E.7)
}


def _create_shooting(client: TestClient, headers: dict) -> dict:
    circuit = client.post(
        "/api/v1/circuits", json={"name": "Circuit Access"}, headers=headers
    ).json()
    now = datetime.datetime.now(datetime.UTC)
    return client.post(
        "/api/v1/shootings",
        json={
            "circuit_id": circuit["id"],
            "title": "Shooting access test",
            "starts_at": now.isoformat(),
            "ends_at": (now + datetime.timedelta(hours=2)).isoformat(),
        },
        headers=headers,
    ).json()


def test_photographer_unassigned_shooting_is_404_not_403(client: TestClient, db_session) -> None:
    owner = make_user(db_session, role="owner", email="owner-a@apex-test.dev")
    photographer = make_user(db_session, role="photographer", email="photog-a@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))

    resp = client.get(f"/api/v1/shootings/{shooting['id']}", headers=auth_headers(photographer))
    # 404, jamais 403 : ne pas révéler l'existence d'une ressource hors périmètre (§3-I).
    assert resp.status_code == 404


def test_photographer_sees_assigned_shooting(client: TestClient, db_session) -> None:
    owner = make_user(db_session, role="owner", email="owner-b@apex-test.dev")
    photographer = make_user(db_session, role="photographer", email="photog-b@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))

    client.put(
        f"/api/v1/shootings/{shooting['id']}/staff",
        json={"user_ids": [photographer.id]},
        headers=auth_headers(owner),
    )

    resp = client.get(f"/api/v1/shootings/{shooting['id']}", headers=auth_headers(photographer))
    assert resp.status_code == 200


def test_photographer_cannot_create_client(client: TestClient, db_session) -> None:
    photographer = make_user(db_session, role="photographer", email="photog-c@apex-test.dev")
    resp = client.post(
        "/api/v1/clients", json={"name": "X", "kind": "team"}, headers=auth_headers(photographer)
    )
    assert resp.status_code == 403


def test_photographer_can_read_client_referential(client: TestClient, db_session) -> None:
    owner = make_user(db_session, role="owner", email="owner-d@apex-test.dev")
    photographer = make_user(db_session, role="photographer", email="photog-d@apex-test.dev")
    client.post(
        "/api/v1/clients", json={"name": "Ecurie X", "kind": "team"}, headers=auth_headers(owner)
    )

    resp = client.get("/api/v1/clients", headers=auth_headers(photographer))
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_photographer_can_write_engagements_on_assigned_shooting(
    client: TestClient, db_session
) -> None:
    owner = make_user(db_session, role="owner", email="owner-e@apex-test.dev")
    photographer = make_user(db_session, role="photographer", email="photog-e@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))
    client.put(
        f"/api/v1/shootings/{shooting['id']}/staff",
        json={"user_ids": [photographer.id]},
        headers=auth_headers(owner),
    )

    resp = client.post(
        f"/api/v1/shootings/{shooting['id']}/engagements",
        json={"car_number": "7"},
        headers=auth_headers(photographer),
    )
    assert resp.status_code == 201


def test_photographer_cannot_write_engagements_on_unassigned_shooting(
    client: TestClient, db_session
) -> None:
    owner = make_user(db_session, role="owner", email="owner-f@apex-test.dev")
    photographer = make_user(db_session, role="photographer", email="photog-f@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))

    resp = client.post(
        f"/api/v1/shootings/{shooting['id']}/engagements",
        json={"car_number": "7"},
        headers=auth_headers(photographer),
    )
    assert resp.status_code == 404


def test_photographer_cannot_patch_another_photographers_camera(
    client: TestClient, db_session
) -> None:
    """Revue J1 (🔴 n°6) — scénario reproduit : le photographe B ne doit pas pouvoir
    régler le décalage d'horloge (ni le fuseau) du boîtier du photographe A.
    """
    photographer_a = make_user(db_session, role="photographer", email="photog-cam-a@apex-test.dev")
    photographer_b = make_user(db_session, role="photographer", email="photog-cam-b@apex-test.dev")

    camera = Camera(exif_serial="SN-CAM-A", owner_user_id=photographer_a.id)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)

    resp = client.patch(
        f"/api/v1/cameras/{camera.id}",
        json={"clock_offset_seconds": 86400},
        headers=auth_headers(photographer_b),
    )
    # 404, jamais 403 (§3-I) : B ne doit même pas savoir que ce boîtier existe.
    assert resp.status_code == 404

    resp_owner = client.patch(
        f"/api/v1/cameras/{camera.id}",
        json={"clock_offset_seconds": 3600},
        headers=auth_headers(photographer_a),
    )
    assert resp_owner.status_code == 200
    assert resp_owner.json()["camera"]["clock_offset_seconds"] == 3600


def test_photographer_does_not_list_another_photographers_camera(
    client: TestClient, db_session
) -> None:
    photographer_a = make_user(db_session, role="photographer", email="photog-cam-c@apex-test.dev")
    photographer_b = make_user(db_session, role="photographer", email="photog-cam-d@apex-test.dev")

    camera = Camera(exif_serial="SN-CAM-C", owner_user_id=photographer_a.id)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)

    resp = client.get("/api/v1/cameras", headers=auth_headers(photographer_b))
    assert resp.status_code == 200
    assert camera.id not in [c["id"] for c in resp.json()]

    resp_owner_view = client.get("/api/v1/cameras", headers=auth_headers(photographer_a))
    assert camera.id in [c["id"] for c in resp_owner_view.json()]


def test_owner_can_patch_any_camera(client: TestClient, db_session) -> None:
    owner = make_user(db_session, role="owner", email="owner-cam@apex-test.dev")
    photographer = make_user(db_session, role="photographer", email="photog-cam-e@apex-test.dev")
    camera = Camera(exif_serial="SN-CAM-E", owner_user_id=photographer.id)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)

    resp = client.patch(
        f"/api/v1/cameras/{camera.id}",
        json={"clock_offset_seconds": 120},
        headers=auth_headers(owner),
    )
    assert resp.status_code == 200


def _upload_one_media(
    client: TestClient, headers: dict, shooting_id: int, key: str = "leak-1"
) -> tuple[int, int]:
    from tests.support.images import make_valid_jpeg

    batch = client.post(
        "/api/v1/batches",
        json={"expected_count": 1, "shooting_hint_id": shooting_id},
        headers=headers,
    ).json()
    resp = client.post(
        f"/api/v1/batches/{batch['id']}/files",
        headers={**headers, "Idempotency-Key": key},
        files={"file": (f"{key}.jpg", make_valid_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 201, resp.text
    return batch["id"], resp.json()["media_id"]


def test_photographer_cannot_read_another_photographers_media_detail(
    client: TestClient, db_session
) -> None:
    """Chasse active de fuite (§3-I) : `GET /media/{id}` est le point d'accès le plus
    sensible du cloisonnement — un média rattaché au shooting de A ne doit jamais être
    lisible par B, même si B connaît (ou devine) son id.
    """
    owner = make_user(db_session, role="owner", email="owner-leak-media@apex-test.dev")
    photographer_a = make_user(db_session, role="photographer", email="photog-leak-a@apex-test.dev")
    photographer_b = make_user(db_session, role="photographer", email="photog-leak-b@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))
    client.put(
        f"/api/v1/shootings/{shooting['id']}/staff",
        json={"user_ids": [photographer_a.id]},
        headers=auth_headers(owner),
    )
    _batch_id, media_id = _upload_one_media(
        client, auth_headers(photographer_a), shooting["id"], key="leak-media-detail"
    )

    resp = client.get(f"/api/v1/media/{media_id}", headers=auth_headers(photographer_b))
    assert resp.status_code == 404

    resp_owner = client.get(f"/api/v1/media/{media_id}", headers=auth_headers(owner))
    assert resp_owner.status_code == 200

    resp_a = client.get(f"/api/v1/media/{media_id}", headers=auth_headers(photographer_a))
    assert resp_a.status_code == 200


def test_photographer_cannot_stream_another_photographers_media_file(
    client: TestClient, db_session
) -> None:
    """Même chasse que ci-dessus, sur le flux binaire médié — c'est l'endpoint qui sert les
    HD/aperçus (§3-H.3) : une fuite ici serait plus grave qu'une fuite de métadonnées.
    """
    owner = make_user(db_session, role="owner", email="owner-leak-file@apex-test.dev")
    photographer_a = make_user(db_session, role="photographer", email="photog-leak-c@apex-test.dev")
    photographer_b = make_user(db_session, role="photographer", email="photog-leak-d@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))
    client.put(
        f"/api/v1/shootings/{shooting['id']}/staff",
        json={"user_ids": [photographer_a.id]},
        headers=auth_headers(owner),
    )
    _batch_id, media_id = _upload_one_media(
        client, auth_headers(photographer_a), shooting["id"], key="leak-media-file"
    )

    resp = client.get(f"/api/v1/media/{media_id}/file/thumb", headers=auth_headers(photographer_b))
    assert resp.status_code == 404


def test_photographer_cannot_attach_media_from_another_photographers_batch(
    client: TestClient, db_session
) -> None:
    """`POST /media/{id}/attach` (rattachement manuel) sur un média hors périmètre doit
    échouer avant même de considérer le shooting cible — sinon B apprendrait que le média
    existe (timing/comportement différent d'un 404 générique)."""
    owner = make_user(db_session, role="owner", email="owner-leak-attach@apex-test.dev")
    photographer_a = make_user(db_session, role="photographer", email="photog-leak-e@apex-test.dev")
    photographer_b = make_user(db_session, role="photographer", email="photog-leak-f@apex-test.dev")
    shooting_a = _create_shooting(client, auth_headers(owner))
    client.put(
        f"/api/v1/shootings/{shooting_a['id']}/staff",
        json={"user_ids": [photographer_a.id]},
        headers=auth_headers(owner),
    )
    _batch_id, media_id = _upload_one_media(
        client, auth_headers(photographer_a), shooting_a["id"], key="leak-media-attach"
    )

    resp = client.post(
        f"/api/v1/media/{media_id}/attach",
        json={"shooting_id": shooting_a["id"]},
        headers=auth_headers(photographer_b),
    )
    assert resp.status_code == 404


def test_photographer_cannot_read_another_photographers_batch_status(
    client: TestClient, db_session
) -> None:
    """`GET /batches/{id}` (suivi de lot, polling) doit rester cloisonné au même titre que
    les médias qu'il contient — sinon B verrait la progression d'un lot de A."""
    owner = make_user(db_session, role="owner", email="owner-leak-batch@apex-test.dev")
    photographer_a = make_user(db_session, role="photographer", email="photog-leak-g@apex-test.dev")
    photographer_b = make_user(db_session, role="photographer", email="photog-leak-h@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))
    client.put(
        f"/api/v1/shootings/{shooting['id']}/staff",
        json={"user_ids": [photographer_a.id]},
        headers=auth_headers(owner),
    )
    batch_id, _media_id = _upload_one_media(
        client, auth_headers(photographer_a), shooting["id"], key="leak-batch-status"
    )
    client.post(f"/api/v1/batches/{batch_id}/close", headers=auth_headers(photographer_a))

    resp = client.get(f"/api/v1/batches/{batch_id}", headers=auth_headers(photographer_b))
    assert resp.status_code == 404

    resp_a = client.get(f"/api/v1/batches/{batch_id}", headers=auth_headers(photographer_a))
    assert resp_a.status_code == 200


def test_photographer_media_list_never_includes_another_photographers_media(
    client: TestClient, db_session
) -> None:
    """`GET /media` (liste, grille principale) — la clause de visibilité doit filtrer à la
    source (SQL), pas seulement bloquer l'accès direct par id."""
    owner = make_user(db_session, role="owner", email="owner-leak-list@apex-test.dev")
    photographer_a = make_user(db_session, role="photographer", email="photog-leak-i@apex-test.dev")
    photographer_b = make_user(db_session, role="photographer", email="photog-leak-j@apex-test.dev")
    shooting = _create_shooting(client, auth_headers(owner))
    client.put(
        f"/api/v1/shootings/{shooting['id']}/staff",
        json={"user_ids": [photographer_a.id]},
        headers=auth_headers(owner),
    )
    _batch_id, media_id = _upload_one_media(
        client, auth_headers(photographer_a), shooting["id"], key="leak-media-list"
    )

    resp = client.get("/api/v1/media", params={"limit": 100}, headers=auth_headers(photographer_b))
    assert resp.status_code == 200
    assert media_id not in [item["id"] for item in resp.json()["items"]]

    resp_a = client.get(
        "/api/v1/media", params={"limit": 100}, headers=auth_headers(photographer_a)
    )
    assert media_id in [item["id"] for item in resp_a.json()["items"]]


def test_users_list_is_owner_only(client: TestClient, db_session) -> None:
    owner = make_user(db_session, role="owner", email="owner-users@apex-test.dev")
    photographer = make_user(db_session, role="photographer", email="photog-users@apex-test.dev")

    resp_photographer = client.get("/api/v1/users", headers=auth_headers(photographer))
    assert resp_photographer.status_code == 403

    resp_owner = client.get("/api/v1/users", headers=auth_headers(owner))
    assert resp_owner.status_code == 200
    emails_by_id = {u["id"]: u["role"] for u in resp_owner.json()}
    assert owner.id in emails_by_id
    assert photographer.id in emails_by_id
    # Réponse restreinte au strict nécessaire (revue J1) : pas d'e-mail exposé.
    assert all("email" not in u for u in resp_owner.json())


#: Préfixes des routeurs réellement implémentés en J1 (logique métier réelle, §4 du plan).
#: Les routeurs J2/J3 encore en squelette `501` (`billing`, `collections`, `review`,
#: `search`, `settings`, `sharing`, `stats`, `dashboard`, `cron`, `demo:seed/reset`)
#: déclarent `Security(bearer_scheme, auto_error=False)` à titre **documentaire** pour
#: l'OpenAPI (choix explicite du lot 0) : ils ne mutent ni n'exposent aucune donnée tant
#: qu'ils répondent `501`, donc l'absence d'un `401` strict sur ces routes n'ouvre aucune
#: fuite — mais ce n'est pas un `401` non plus. Signalé pour les lots J2/J3 : câbler
#: `CurrentUser`/`require_role` dès l'implémentation réelle de chacun de ces routeurs.
J1_IMPLEMENTED_PREFIXES = (
    "/api/v1/auth/me",
    "/api/v1/clients",
    "/api/v1/circuits",
    "/api/v1/drivers",
    "/api/v1/teams",
    "/api/v1/shootings",
    "/api/v1/engagements",
    "/api/v1/batches",
    "/api/v1/media",
    "/api/v1/cameras",
    "/api/v1/users",
    "/api/v1/queue/stats",
)


def test_all_routes_require_auth_except_whitelist(client: TestClient) -> None:
    """Parcourt l'OpenAPI courant (§3-I), scope J1 : aucune route à logique réelle n'est
    accessible sans jeton — sinon `401`/`422` attendus (jamais `200`/`404` qui trahirait un
    accès accepté ou un chemin mal formé plutôt qu'un refus d'authentification).
    """
    openapi = client.get("/openapi.json").json()
    checked = 0
    for path, methods in openapi["paths"].items():
        if not path.startswith(J1_IMPLEMENTED_PREFIXES):
            continue
        for method in methods:
            if method.upper() not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                continue
            if (method.upper(), path) in PUBLIC_PATHS:
                continue
            checked += 1
            # Chemins paramétrés : {id} suffit, la ressource n'a pas besoin d'exister —
            # une 401 doit intervenir avant toute résolution de ressource.
            concrete_path = path
            for param in (
                "{client_id}",
                "{circuit_id}",
                "{driver_id}",
                "{team_id}",
                "{shooting_id}",
                "{engagement_id}",
                "{batch_id}",
                "{media_id}",
                "{camera_id}",
                "{variant}",
                "{engagement_id}",
            ):
                concrete_path = concrete_path.replace(param, "1")
            resp = client.request(method.upper(), concrete_path)
            assert resp.status_code in (401, 422), (
                f"{method.upper()} {path} accessible sans authentification "
                f"(status={resp.status_code})"
            )
    assert checked > 10, "le sweep n'a couvert presque aucune route — vérifier l'OpenAPI"
