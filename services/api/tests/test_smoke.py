"""Fumée : la fixture de base migrée et le client HTTP fonctionnent."""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, make_user


def test_health_is_public(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_protected_route_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/clients")
    assert resp.status_code == 401


def test_login_flow(client: TestClient, db_session) -> None:
    user = make_user(db_session, role="owner", email="owner@apex-test.dev")
    resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Test1234!"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "owner"

    me = client.get("/api/v1/auth/me", headers=auth_headers(user))
    assert me.status_code == 200
    assert me.json()["email"] == user.email
