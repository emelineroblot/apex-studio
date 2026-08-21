"""Filtre `is_simulated` de `GET /search` (revue J2, 🟠 n°1, §3-N.1 du plan) — mono-sélection
à 3 états : `None`/absent = tous, `false` = réels seulement, `true` = simulés seulement.

Contrat câblé côté frontend par anticipation (`FacetOriginToggle`, `apps/web/src/lib/api/
resources/search.ts`) : ces tests verrouillent qu'il répond bien tel que documenté, sur
`GET /search` et sur `POST /collections/{id}/items {from_search: …}` qui partage les mêmes
filtres.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from apex.services.search_projection import project_media_search
from tests.conftest import auth_headers, make_user
from tests.search.factories import (
    make_circuit,
    make_client,
    make_media,
    make_shooting,
    make_upload_batch,
)


@pytest.fixture
def mixed_origin_dataset(db_session: Session):
    owner = make_user(db_session, role="owner")
    circuit = make_circuit(db_session, "Circuit Origine")
    demo_client = make_client(db_session, "Client Origine")
    shooting = make_shooting(
        db_session, client=demo_client, circuit=circuit, starts_at=datetime(2026, 5, 1, tzinfo=UTC)
    )
    batch = make_upload_batch(db_session, user=owner)

    make_media(db_session, batch=batch, user=owner, shooting=shooting, shot_at=datetime.now(UTC))
    make_media(db_session, batch=batch, user=owner, shooting=shooting, shot_at=datetime.now(UTC))
    simulated1 = make_media(
        db_session, batch=batch, user=owner, shooting=shooting, shot_at=datetime.now(UTC)
    )
    simulated1.is_simulated = True
    simulated2 = make_media(
        db_session, batch=batch, user=owner, shooting=shooting, shot_at=datetime.now(UTC)
    )
    simulated2.is_simulated = True
    simulated3 = make_media(
        db_session, batch=batch, user=owner, shooting=shooting, shot_at=datetime.now(UTC)
    )
    simulated3.is_simulated = True

    db_session.commit()
    project_media_search(db_session, None)
    db_session.commit()

    return {"owner": owner, "client_id": demo_client.id}


class TestOriginFilterThreeStates:
    def test_no_filter_returns_every_media_regardless_of_origin(
        self, client, mixed_origin_dataset
    ) -> None:
        headers = auth_headers(mixed_origin_dataset["owner"])
        payload = client.get("/api/v1/search", headers=headers).json()
        assert payload["total"] == 5

    def test_is_simulated_false_returns_real_media_only(self, client, mixed_origin_dataset) -> None:
        headers = auth_headers(mixed_origin_dataset["owner"])
        payload = client.get(
            "/api/v1/search", headers=headers, params={"is_simulated": "false"}
        ).json()
        assert payload["total"] == 2
        assert all(item["is_simulated"] is False for item in payload["items"])

    def test_is_simulated_true_returns_simulated_media_only(
        self, client, mixed_origin_dataset
    ) -> None:
        headers = auth_headers(mixed_origin_dataset["owner"])
        payload = client.get(
            "/api/v1/search", headers=headers, params={"is_simulated": "true"}
        ).json()
        assert payload["total"] == 3
        assert all(item["is_simulated"] is True for item in payload["items"])

    def test_from_search_composition_honours_the_same_filter(
        self, client, db_session, mixed_origin_dataset
    ) -> None:
        """`POST /collections/{id}/items {from_search: …}` partage le contrat de `GET /search`
        (§3-K) — le filtre d'origine doit y être branché lui aussi, pas seulement sur la
        recherche interactive.
        """
        headers = auth_headers(mixed_origin_dataset["owner"])
        collection = client.post(
            "/api/v1/collections",
            json={"client_id": mixed_origin_dataset["client_id"], "title": "Réels seulement"},
            headers=headers,
        ).json()
        resp = client.post(
            f"/api/v1/collections/{collection['id']}/items",
            json={"from_search": {"is_simulated": False}},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text
        assert resp.json()["added"] == 2
