"""Lien de partage et session client (§3-L) — création, échange, expiration, révocation.

Ce que ces tests protègent, dans l'ordre d'importance : un jeton qui ne se retrouve nulle
part ailleurs qu'à la création, une révocation qui prend effet tout de suite, et un lien
mort qui répond `410` avec un corps métier — jamais une trace technique, c'est un critère
d'acceptation du brief.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from apex.models.billing import ShareLink
from apex.services import sharing
from tests.conftest import auth_headers
from tests.public.conftest import expire_link


class TestCreationDuLien:
    def test_le_jeton_en_clair_nest_renvoye_qua_la_creation(
        self, client, shared_collection, db_session
    ) -> None:
        headers = auth_headers(shared_collection["owner"])
        collection_id = shared_collection["collection"].id

        created = client.post(
            f"/api/v1/collections/{collection_id}/share-links",
            json={"expires_in_days": 7},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        token = created.json()["token"]
        assert created.json()["url"].endswith(f"/c/{token}")

        # La base ne porte que l'empreinte : même en lisant la ligne, on ne peut pas
        # reconstituer le lien.
        stored = db_session.execute(
            select(ShareLink).where(ShareLink.token_hash == sharing.hash_token(token))
        ).scalar_one()
        assert stored.token_hash != token.encode()

        listed = client.get(
            f"/api/v1/collections/{collection_id}/share-links", headers=headers
        ).json()
        assert all(token not in entry["url_masked"] for entry in listed)

    def test_un_photographe_ne_peut_pas_partager(self, client, shared_collection) -> None:
        resp = client.post(
            f"/api/v1/collections/{shared_collection['collection'].id}/share-links",
            json={"expires_in_days": 7},
            headers=auth_headers(shared_collection["photographer"]),
        )
        assert resp.status_code == 403, resp.text

    def test_une_duree_aberrante_est_refusee(self, client, shared_collection) -> None:
        resp = client.post(
            f"/api/v1/collections/{shared_collection['collection'].id}/share-links",
            json={"expires_in_days": 3650},
            headers=auth_headers(shared_collection["owner"]),
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "invalid_expiry"


class TestEchangeDeJeton:
    def test_le_jeton_ouvre_une_session_et_decrit_la_collection(
        self, client, shared_collection
    ) -> None:
        resp = client.post("/api/v1/public/session", json={"token": shared_collection["token"]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["expires_in"] == 30 * 60
        assert body["collection"]["title"] == "Sélection Grand Prix"
        assert body["collection"]["item_count"] == 3
        assert body["collection"]["studio_name"]

    def test_un_jeton_inconnu_est_introuvable_pas_interdit(self, client, shared_collection) -> None:
        resp = client.post("/api/v1/public/session", json={"token": "jeton-invente"})
        assert resp.status_code == 404, resp.text

    def test_l_ouverture_de_session_compte_une_vue(
        self, client, shared_collection, db_session
    ) -> None:
        for _ in range(2):
            client.post("/api/v1/public/session", json={"token": shared_collection["token"]})
        link = db_session.get(ShareLink, shared_collection["link_id"])
        db_session.refresh(link)
        assert link.view_count == 2
        assert link.last_seen_at is not None

    def test_un_lien_expire_repond_410_avec_un_corps_metier(
        self, client, shared_collection, db_session
    ) -> None:
        expire_link(db_session, shared_collection["link_id"])
        resp = client.post("/api/v1/public/session", json={"token": shared_collection["token"]})
        assert resp.status_code == 410, resp.text
        # Un code exploitable par l'écran dédié et un message déjà présentable : aucune
        # trace technique ne doit pouvoir s'afficher devant un client.
        body = resp.json()
        assert body["code"] == "link_expired"
        assert "n'est plus valide" in body["message"]


class TestRevocation:
    def test_la_revocation_coupe_une_session_deja_ouverte(
        self, client, shared_collection, client_session
    ) -> None:
        headers = client_session["headers"]
        assert client.get("/api/v1/public/collection", headers=headers).status_code == 200

        revoked = client.delete(
            f"/api/v1/share-links/{shared_collection['link_id']}",
            headers=auth_headers(shared_collection["owner"]),
        )
        assert revoked.status_code == 204, revoked.text

        # Le JWT de session est toujours valide 30 minutes — c'est précisément pour cela
        # que le lien est relu à chaque requête. Sans cette relecture, le client garderait
        # l'accès une demi-heure après la révocation.
        after = client.get("/api/v1/public/collection", headers=headers)
        assert after.status_code == 410
        assert after.json()["code"] == "link_expired"

    def test_revoquer_deux_fois_ne_repousse_pas_la_date(
        self, client, shared_collection, db_session
    ) -> None:
        headers = auth_headers(shared_collection["owner"])
        url = f"/api/v1/share-links/{shared_collection['link_id']}"
        client.delete(url, headers=headers)
        link = db_session.get(ShareLink, shared_collection["link_id"])
        db_session.refresh(link)
        first = link.revoked_at

        client.delete(url, headers=headers)
        db_session.refresh(link)
        assert link.revoked_at == first

    def test_un_photographe_ne_peut_pas_revoquer(self, client, shared_collection) -> None:
        resp = client.delete(
            f"/api/v1/share-links/{shared_collection['link_id']}",
            headers=auth_headers(shared_collection["photographer"]),
        )
        assert resp.status_code == 403, resp.text


class TestExpirationCoteService:
    def test_un_lien_expire_a_la_seconde_pres_est_deja_mort(self, db_session, shared_collection):
        """La comparaison est stricte : un lien dont l'échéance vient d'être atteinte est
        expiré, pas encore valide une dernière fois."""
        link = db_session.get(ShareLink, shared_collection["link_id"])
        link.expires_at = datetime.now(UTC) - timedelta(microseconds=1)
        db_session.commit()
        try:
            sharing.assert_usable(link)
        except sharing.ShareLinkExpired:
            return
        raise AssertionError("un lien échu doit être refusé")
