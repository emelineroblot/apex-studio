"""Sélection du client (§3-L, contrat `/public/selection/**`).

Ce que ces tests tiennent : la sélection naît au premier clic (jamais avant, sinon on ne
distingue plus « pas encore ouvert » de « tout décoché »), les écritures sont idempotentes
parce que l'UI enregistre de façon optimiste et rejoue, et le périmètre du jeton s'applique
ici comme partout ailleurs.
"""

from __future__ import annotations

from sqlalchemy import select

from apex.models.billing import ClientSelection, SelectionItem
from tests.conftest import auth_headers


def _item_url(media_id: int) -> str:
    return f"/api/v1/public/selection/items/{media_id}"


class TestNaissanceDeLaSelection:
    def test_aucune_selection_avant_le_premier_clic(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        response = client.get("/api/v1/public/selection", headers=client_session["headers"])
        assert response.status_code == 200
        assert response.json() == {"status": "open", "count": 0, "items": []}
        assert (
            db_session.execute(
                select(ClientSelection).where(
                    ClientSelection.collection_id == shared_collection["collection"].id
                )
            ).scalar_one_or_none()
            is None
        )

    def test_le_premier_clic_cree_la_selection(
        self, client, shared_collection, client_session
    ) -> None:
        media_id = shared_collection["media_ids"][0]
        response = client.put(
            _item_url(media_id),
            json={"comment": "  la meilleure  "},
            headers=client_session["headers"],
        )
        assert response.status_code == 200, response.text
        # Le commentaire est nettoyé à l'entrée : un champ rempli d'espaces vaut vide.
        assert response.json() == {"selected": True, "comment": "la meilleure"}

        listed = client.get("/api/v1/public/selection", headers=client_session["headers"]).json()
        assert listed["count"] == 1
        assert listed["items"] == [{"media_id": media_id, "comment": "la meilleure"}]


class TestIdempotence:
    def test_recocher_met_a_jour_sans_dupliquer(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        media_id = shared_collection["media_ids"][0]
        headers = client_session["headers"]
        client.put(_item_url(media_id), json={"comment": "un"}, headers=headers)
        client.put(_item_url(media_id), json={"comment": "deux"}, headers=headers)

        rows = (
            db_session.execute(select(SelectionItem).where(SelectionItem.media_id == media_id))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].comment == "deux"

    def test_decocher_deux_fois_nest_pas_une_erreur(
        self, client, shared_collection, client_session
    ) -> None:
        media_id = shared_collection["media_ids"][0]
        headers = client_session["headers"]
        client.put(_item_url(media_id), json={}, headers=headers)
        assert client.delete(_item_url(media_id), headers=headers).status_code == 204
        assert client.delete(_item_url(media_id), headers=headers).status_code == 204

    def test_decocher_avant_toute_selection_nest_pas_une_erreur(
        self, client, shared_collection, client_session
    ) -> None:
        """L'état voulu — cette photo n'est pas sélectionnée — est déjà atteint."""
        response = client.delete(
            _item_url(shared_collection["media_ids"][1]), headers=client_session["headers"]
        )
        assert response.status_code == 204


class TestPerimetre:
    def test_une_photo_dune_autre_collection_est_introuvable(
        self, client, shared_collection, client_session
    ) -> None:
        response = client.put(
            _item_url(shared_collection["outsider_media_id"]),
            json={},
            headers=client_session["headers"],
        )
        assert response.status_code == 404

    def test_la_selection_est_visible_du_studio(
        self, client, shared_collection, client_session
    ) -> None:
        media_id = shared_collection["media_ids"][2]
        client.put(
            _item_url(media_id), json={"comment": "celle-ci"}, headers=client_session["headers"]
        )

        studio = client.get(
            f"/api/v1/collections/{shared_collection['collection'].id}/selection",
            headers=auth_headers(shared_collection["owner"]),
        )
        assert studio.status_code == 200, studio.text
        body = studio.json()
        assert body["status"] == "open"
        assert body["count"] == 1
        assert body["items"] == [{"media_id": media_id, "comment": "celle-ci"}]


class TestFiltreSelectionUniquement:
    def test_la_galerie_peut_se_limiter_aux_photos_cochees(
        self, client, shared_collection, client_session
    ) -> None:
        headers = client_session["headers"]
        chosen = shared_collection["media_ids"][1]
        client.put(_item_url(chosen), json={}, headers=headers)

        response = client.get(
            "/api/v1/public/collection", params={"selected_only": True}, headers=headers
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert [item["media_id"] for item in items] == [chosen]
        assert items[0]["selected"] is True

    def test_la_galerie_complete_marque_les_photos_cochees(
        self, client, shared_collection, client_session
    ) -> None:
        headers = client_session["headers"]
        chosen = shared_collection["media_ids"][1]
        client.put(_item_url(chosen), json={"comment": "oui"}, headers=headers)

        items = client.get("/api/v1/public/collection", headers=headers).json()["items"]
        by_id = {item["media_id"]: item for item in items}
        assert by_id[chosen]["selected"] is True
        assert by_id[chosen]["comment"] == "oui"
        others = [item for media_id, item in by_id.items() if media_id != chosen]
        assert all(item["selected"] is False and item["comment"] is None for item in others)
