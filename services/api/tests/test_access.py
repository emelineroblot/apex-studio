"""Cloisonnement des rôles (§3-I du plan) — matrice `owner`/`photographer` et exhaustivité
de l'authentification sur les routes internes.
"""

from __future__ import annotations

import datetime

from fastapi.testclient import TestClient

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
