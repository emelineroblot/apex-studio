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


def test_health_signale_la_base_et_le_stockage(client: TestClient) -> None:
    """Le contrôle de santé couvre les deux dépendances externes de l'application.

    `storage` valait `"unknown"` en dur jusqu'au premier déploiement : un contrôle qui
    ignore la moitié de ce dont l'application dépend n'aide pas à diagnostiquer une clé
    d'accès invalide ou un bucket disparu — les deux pannes les plus probables en ligne.
    """
    body = client.get("/api/v1/health").json()
    assert body["db"] == "ok"
    assert body["storage"] == "ok"
    assert body["status"] == "ok"


def test_health_degrade_quand_le_stockage_repond_plus(client: TestClient, monkeypatch) -> None:
    """Une panne de stockage doit se voir dans `status`, pas seulement dans le détail."""
    import apex.main

    def _boom() -> None:
        raise RuntimeError("stockage injoignable")

    monkeypatch.setattr(apex.main, "get_storage_client", _boom)
    body = client.get("/api/v1/health").json()
    assert body["storage"] == "down"
    assert body["status"] == "degraded"
    # La base, elle, reste joignable : le diagnostic doit rester lisible dépendance par
    # dépendance, jamais réduit à un seul drapeau.
    assert body["db"] == "ok"


def test_le_demarrage_survit_a_une_base_injoignable(monkeypatch) -> None:
    """Un bootstrap optionnel ne doit jamais empêcher l'application de démarrer.

    Le hook levait, et l'API entière refusait de se lancer dès que la base hoquetait —
    `GET /health` compris, c'est-à-dire l'endpoint censé dire *ce qui* ne va pas. Constaté
    en production : le pooler à court de connexions rendait l'application totalement
    muette au lieu de dégradée.
    """
    import apex.main

    def _sessions_en_panne() -> None:
        raise RuntimeError("pooler injoignable")

    monkeypatch.setattr(apex.main, "SessionLocal", _sessions_en_panne)
    # Ne lève pas : l'échec est consigné, le démarrage se poursuit.
    apex.main._bootstrap_demo_users()
