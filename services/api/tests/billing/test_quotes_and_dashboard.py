"""Devis (§3-O) et tableau de bord (§3, contrat J3).

Le devis n'est pas un document isolé : l'accepter **crée le shooting**, avec la même
période. C'est ce qui fait que les photos du week-end se rattacheront toutes seules — un
décalage d'une minute entre le devis et le shooting ressaisi à la main, et elles ne se
rattachent plus.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from apex.models.shooting import Shooting
from tests.conftest import auth_headers, make_user
from tests.search.factories import make_circuit, make_client


@pytest.fixture
def quote_context(db_session: Session) -> dict:
    owner = make_user(db_session, role="owner", email="owner-quotes@apex-test.dev")
    photographer = make_user(
        db_session, role="photographer", email="photographer-quotes@apex-test.dev"
    )
    circuit = make_circuit(db_session, "Circuit Devis")
    demo_client = make_client(db_session, "Client Devis")
    db_session.commit()
    return {
        "owner": owner,
        "photographer": photographer,
        "circuit_id": circuit.id,
        "client_id": demo_client.id,
    }


def _payload(quote_context: dict, **overrides) -> dict:
    start = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)
    payload = {
        "client_id": quote_context["client_id"],
        "circuit_id": quote_context["circuit_id"],
        "title": "Week-end GT — Magny-Cours",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=10)).isoformat(),
        "amount_cents": 180000,
    }
    payload.update(overrides)
    return payload


class TestCreation:
    def test_un_devis_est_cree_en_brouillon(self, client, quote_context) -> None:
        response = client.post(
            "/api/v1/quotes",
            json=_payload(quote_context),
            headers=auth_headers(quote_context["owner"]),
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "draft"
        assert response.json()["created_shooting_id"] is None

    def test_une_periode_inversee_est_refusee(self, client, quote_context) -> None:
        start = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)
        response = client.post(
            "/api/v1/quotes",
            json=_payload(
                quote_context,
                starts_at=start.isoformat(),
                ends_at=(start - timedelta(hours=1)).isoformat(),
            ),
            headers=auth_headers(quote_context["owner"]),
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_period"

    def test_un_client_inconnu_est_refuse(self, client, quote_context) -> None:
        response = client.post(
            "/api/v1/quotes",
            json=_payload(quote_context, client_id=999_999),
            headers=auth_headers(quote_context["owner"]),
        )
        assert response.status_code == 404

    def test_un_photographe_ne_peut_pas_etablir_un_devis(self, client, quote_context) -> None:
        response = client.post(
            "/api/v1/quotes",
            json=_payload(quote_context),
            headers=auth_headers(quote_context["photographer"]),
        )
        assert response.status_code == 403


class TestAcceptation:
    def test_accepter_cree_le_shooting_avec_la_meme_periode(
        self, client, quote_context, db_session
    ) -> None:
        headers = auth_headers(quote_context["owner"])
        quote = client.post("/api/v1/quotes", json=_payload(quote_context), headers=headers).json()

        response = client.post(f"/api/v1/quotes/{quote['id']}/accept", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["quote"]["status"] == "accepted"
        assert body["quote"]["accepted_at"] is not None

        shooting = db_session.get(Shooting, body["created_shooting"]["id"])
        assert shooting is not None
        assert shooting.status == "planned"
        # La période est reprise à l'identique : c'est elle qui rattachera les photos.
        # Comparaison sur des `datetime`, jamais sur des chaînes — le contrat sérialise en
        # `Z` là où `isoformat()` écrit `+00:00`, pour le même instant.
        assert shooting.starts_at == datetime.fromisoformat(quote["starts_at"])
        assert shooting.ends_at == datetime.fromisoformat(quote["ends_at"])
        assert shooting.client_id == quote_context["client_id"]

    def test_accepter_deux_fois_ne_cree_quun_shooting(
        self, client, quote_context, db_session
    ) -> None:
        """Deux shootings pour un devis, ce sont des photos qui se rattachent à l'un ou à
        l'autre selon l'ordre des identifiants."""
        headers = auth_headers(quote_context["owner"])
        quote = client.post("/api/v1/quotes", json=_payload(quote_context), headers=headers).json()

        first = client.post(f"/api/v1/quotes/{quote['id']}/accept", headers=headers).json()
        second = client.post(f"/api/v1/quotes/{quote['id']}/accept", headers=headers).json()
        assert first["created_shooting"]["id"] == second["created_shooting"]["id"]

    def test_un_photographe_ne_peut_pas_accepter(self, client, quote_context) -> None:
        headers = auth_headers(quote_context["owner"])
        quote = client.post("/api/v1/quotes", json=_payload(quote_context), headers=headers).json()
        response = client.post(
            f"/api/v1/quotes/{quote['id']}/accept",
            headers=auth_headers(quote_context["photographer"]),
        )
        assert response.status_code == 403


class TestDashboard:
    def test_les_quatre_indicateurs_sont_lus_tels_quels(self, client, quote_context) -> None:
        headers = auth_headers(quote_context["owner"])
        response = client.get("/api/v1/dashboard", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {
            "revenue_cents",
            "shootings_done",
            "shootings_upcoming",
            "media_ingested",
            "auto_attach_rate",
        }
        assert set(body["media_ingested"]) == {"real", "simulated", "total"}

    def test_un_shooting_a_venir_est_compte_apres_acceptation(self, client, quote_context) -> None:
        headers = auth_headers(quote_context["owner"])
        before = client.get("/api/v1/dashboard", headers=headers).json()["shootings_upcoming"]

        quote = client.post("/api/v1/quotes", json=_payload(quote_context), headers=headers).json()
        client.post(f"/api/v1/quotes/{quote['id']}/accept", headers=headers)

        after = client.get("/api/v1/dashboard", headers=headers).json()["shootings_upcoming"]
        assert after == before + 1

    def test_une_borne_de_date_illisible_est_refusee(self, client, quote_context) -> None:
        """Afficher tout l'historique quand on demande « ce mois-ci » est pire qu'une erreur."""
        response = client.get(
            "/api/v1/dashboard",
            params={"from": "hier"},
            headers=auth_headers(quote_context["owner"]),
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_date"

    def test_le_tableau_de_bord_est_reserve_au_dirigeant(self, client, quote_context) -> None:
        response = client.get(
            "/api/v1/dashboard", headers=auth_headers(quote_context["photographer"])
        )
        assert response.status_code == 403
