"""Variantes d'image servies au client (§3-H.2, §3-H.3).

L'écart laissé ouvert en revue J1 se referme ici : la vignette **stockée** reste propre —
pHash et netteté sont calculés dessus — et c'est la copie **servie** qui est filigranée, à
la volée. Ces tests vérifient les deux moitiés de cette phrase.

Le HD n'a volontairement aucune route ici : il ne sort que par l'archive, après validation.
"""

from __future__ import annotations

import io

from PIL import Image

from apex.services.storage import get_storage_client


def _variant_url(media_id: int, variant: str) -> str:
    return f"/api/v1/public/media/{media_id}/file/{variant}"


class TestVignetteFiligranee:
    def test_la_vignette_servie_differe_de_la_vignette_stockee(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        media_id = shared_collection["media_ids"][0]
        response = client.get(_variant_url(media_id, "thumb"), headers=client_session["headers"])
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/webp"

        from apex.models.media import Media

        stored_key = db_session.get(Media, media_id).storage_key_thumb
        stored = b"".join(get_storage_client().open_stream(stored_key).chunks)
        # Le filigrane est appliqué sur la copie transmise, jamais sur celle qui sert au
        # calcul du pHash et de la netteté.
        assert response.content != stored

    def test_la_vignette_servie_reste_une_image_valide(
        self, client, shared_collection, client_session
    ) -> None:
        response = client.get(
            _variant_url(shared_collection["media_ids"][0], "thumb"),
            headers=client_session["headers"],
        )
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.format == "WEBP"
            assert image.size == (320, 213)

    def test_l_apercu_est_servi_tel_quel(self, client, shared_collection, client_session) -> None:
        """L'aperçu porte déjà son filigrane, cuit à l'ingestion : le re-filigraner
        coûterait un décodage/ré-encodage par requête pour rien."""
        media_id = shared_collection["media_ids"][0]
        response = client.get(_variant_url(media_id, "preview"), headers=client_session["headers"])
        assert response.status_code == 200
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.size == (1600, 1067)


class TestCacheEtEmpreintes:
    def test_vignette_et_apercu_nont_pas_le_meme_etag(
        self, client, shared_collection, client_session
    ) -> None:
        """Sans le suffixe de variante, deux images du même média partageraient une
        empreinte et le navigateur servirait l'une pour l'autre."""
        media_id = shared_collection["media_ids"][0]
        headers = client_session["headers"]
        thumb = client.get(_variant_url(media_id, "thumb"), headers=headers)
        preview = client.get(_variant_url(media_id, "preview"), headers=headers)
        assert thumb.headers["etag"] != preview.headers["etag"]

    def test_une_empreinte_connue_evite_un_second_transfert(
        self, client, shared_collection, client_session
    ) -> None:
        media_id = shared_collection["media_ids"][0]
        headers = dict(client_session["headers"])
        first = client.get(_variant_url(media_id, "thumb"), headers=headers)
        again = client.get(
            _variant_url(media_id, "thumb"),
            headers={**headers, "If-None-Match": first.headers["etag"]},
        )
        assert again.status_code == 304
        assert again.content == b""


class TestPerimetre:
    def test_un_media_dune_autre_collection_est_introuvable(
        self, client, shared_collection, client_session
    ) -> None:
        response = client.get(
            _variant_url(shared_collection["outsider_media_id"], "thumb"),
            headers=client_session["headers"],
        )
        assert response.status_code == 404

    def test_un_media_inexistant_est_introuvable(
        self, client, shared_collection, client_session
    ) -> None:
        response = client.get(_variant_url(999_999, "preview"), headers=client_session["headers"])
        assert response.status_code == 404

    def test_aucune_route_hd_nexiste_cote_client(self, client) -> None:
        spec = client.get("/openapi.json").json()
        assert not [
            path for path in spec["paths"] if path.startswith("/api/v1/public/") and "hd" in path
        ]
