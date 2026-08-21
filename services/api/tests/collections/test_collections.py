"""Collections (J2, §3-K du plan) — composition depuis une sélection explicite ou depuis une
recherche, publication, cloisonnement (§3-I : dirigeant lecture/écriture, photographe lecture
seule).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from apex.services.search_projection import project_media_search
from tests.conftest import auth_headers, make_user
from tests.search.factories import (
    make_camera,
    make_circuit,
    make_client,
    make_media,
    make_shooting,
    make_upload_batch,
)


@pytest.fixture
def collection_dataset(db_session: Session):
    owner = make_user(db_session, role="owner", email="owner-collections@apex-test.dev")
    photographer = make_user(
        db_session, role="photographer", email="photographer-collections@apex-test.dev"
    )
    circuit = make_circuit(db_session, "Circuit Collections")
    demo_client = make_client(db_session, "Client Collections")
    camera = make_camera(db_session)
    base = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
    batch = make_upload_batch(db_session, user=owner)

    media_ids = [
        make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            camera=camera,
            shot_at=base,
            attachment_status="shooting_attached",
            attachment_source="pipeline_time",
        ).id
        for _ in range(4)
    ]
    db_session.commit()
    project_media_search(db_session, None)
    db_session.commit()

    return {
        "owner": owner,
        "photographer": photographer,
        "client_id": demo_client.id,
        "shooting_id": shooting.id,
        "media_ids": media_ids,
    }


class TestCollectionCloisonnement:
    def test_owner_can_create_a_collection(self, client, collection_dataset) -> None:
        headers = auth_headers(collection_dataset["owner"])
        resp = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "Sélection presse"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "draft"

    def test_photographer_cannot_create_a_collection(self, client, collection_dataset) -> None:
        headers = auth_headers(collection_dataset["photographer"])
        resp = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "Sélection presse"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_photographer_can_still_list_and_read_collections(
        self, client, collection_dataset
    ) -> None:
        owner_headers = auth_headers(collection_dataset["owner"])
        created = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "Lecture seule"},
            headers=owner_headers,
        ).json()

        photographer_headers = auth_headers(collection_dataset["photographer"])
        listing = client.get("/api/v1/collections", headers=photographer_headers)
        assert listing.status_code == 200
        assert any(c["id"] == created["id"] for c in listing.json()["items"])

        detail = client.get(f"/api/v1/collections/{created['id']}", headers=photographer_headers)
        assert detail.status_code == 200


class TestCollectionComposition:
    def test_composing_from_an_explicit_selection_deduplicates(
        self, client, collection_dataset
    ) -> None:
        headers = auth_headers(collection_dataset["owner"])
        media_ids = collection_dataset["media_ids"]
        collection = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "Sélection explicite"},
            headers=headers,
        ).json()

        resp = client.post(
            f"/api/v1/collections/{collection['id']}/items",
            json={"media_ids": [media_ids[0], media_ids[1], media_ids[0]]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        # Le doublon intra-requête est absorbé côté client (dédoublonnage), le deuxième
        # appel avec un média déjà présent doit être compté comme doublon côté serveur.
        assert resp.json()["added"] == 2

        resp2 = client.post(
            f"/api/v1/collections/{collection['id']}/items",
            json={"media_ids": [media_ids[0], media_ids[2]]},
            headers=headers,
        )
        assert resp2.json() == {"added": 1, "skipped_duplicates": 1}

        detail = client.get(f"/api/v1/collections/{collection['id']}", headers=headers).json()
        assert {item["media_id"] for item in detail["items"]} == set(media_ids[:3])

    def test_composing_from_a_search_query_adds_every_matching_media(
        self, client, collection_dataset
    ) -> None:
        headers = auth_headers(collection_dataset["owner"])
        collection = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "Depuis la recherche"},
            headers=headers,
        ).json()

        resp = client.post(
            f"/api/v1/collections/{collection['id']}/items",
            json={"from_search": {"shooting_id": [collection_dataset["shooting_id"]]}},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["added"] == len(collection_dataset["media_ids"])

    def test_an_unknown_media_id_is_skipped_not_a_server_error(
        self, client, collection_dataset
    ) -> None:
        """Revue J2 (🟡 13) : `on_conflict_do_nothing` ne couvre que les doublons, pas une
        violation de FK vers `media` — un id inexistant levait un `500`.
        """
        headers = auth_headers(collection_dataset["owner"])
        media_ids = collection_dataset["media_ids"]
        collection = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "Id inconnu"},
            headers=headers,
        ).json()

        resp = client.post(
            f"/api/v1/collections/{collection['id']}/items",
            json={"media_ids": [media_ids[0], 999_999_999]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["added"] == 1

        detail = client.get(f"/api/v1/collections/{collection['id']}", headers=headers).json()
        assert {item["media_id"] for item in detail["items"]} == {media_ids[0]}

    def test_a_malformed_from_search_filter_is_a_422_not_a_500(
        self, client, collection_dataset
    ) -> None:
        """Revue J2 (🟡 12) : `from_search` est désormais validé par Pydantic
        (`FromSearchFilters`) — un champ mal typé est refusé en amont, jamais une exception
        SQL non capturée en aval de `services/facets.py`.
        """
        headers = auth_headers(collection_dataset["owner"])
        collection = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "Filtre invalide"},
            headers=headers,
        ).json()

        resp = client.post(
            f"/api/v1/collections/{collection['id']}/items",
            # `shooting_id` doit être une liste d'entiers, pas une chaîne libre.
            json={"from_search": {"shooting_id": "pas-un-entier"}},
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

    def test_removing_an_item_and_publishing(self, client, collection_dataset) -> None:
        headers = auth_headers(collection_dataset["owner"])
        media_ids = collection_dataset["media_ids"]
        collection = client.post(
            "/api/v1/collections",
            json={"client_id": collection_dataset["client_id"], "title": "À publier"},
            headers=headers,
        ).json()
        client.post(
            f"/api/v1/collections/{collection['id']}/items",
            json={"media_ids": media_ids},
            headers=headers,
        )

        resp = client.delete(
            f"/api/v1/collections/{collection['id']}/items/{media_ids[0]}", headers=headers
        )
        assert resp.status_code == 204

        detail = client.get(f"/api/v1/collections/{collection['id']}", headers=headers).json()
        assert media_ids[0] not in {item["media_id"] for item in detail["items"]}
        assert len(detail["items"]) == len(media_ids) - 1

        published = client.post(
            f"/api/v1/collections/{collection['id']}/publish", headers=headers
        ).json()
        assert published["status"] == "published"
        assert published["published_at"] is not None

        # Idempotent : republier une collection déjà publiée ne lève pas d'erreur.
        republished = client.post(
            f"/api/v1/collections/{collection['id']}/publish", headers=headers
        ).json()
        assert republished["status"] == "published"
