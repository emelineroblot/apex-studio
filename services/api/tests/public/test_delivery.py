"""Validation de la sélection, préparation et téléchargement de l'archive (§3-M, §3-O).

Le chemin complet, du clic « je valide » au fichier `.zip` : la validation ne fait
qu'enregistrer et mettre deux travaux en file, le worker prépare, et le HD ne sort qu'une
fois les deux conditions réunies — sélection validée **et** livraison prête.
"""

from __future__ import annotations

import io
import zipfile

from sqlalchemy import select

from apex.db import SessionLocal
from apex.models.billing import Delivery, Invoice, InvoiceLine
from apex.models.job import Job
from apex.queue.runner import drain
from tests.conftest import auth_headers

ARCHIVE_URL = "/api/v1/public/delivery/archive"
VALIDATE_URL = "/api/v1/public/selection/validate"


def _select(client, headers, media_ids: list[int]) -> None:
    for media_id in media_ids:
        response = client.put(
            f"/api/v1/public/selection/items/{media_id}", json={}, headers=headers
        )
        assert response.status_code == 200, response.text


def _drain() -> None:
    result = drain(SessionLocal, "test-delivery-worker", deadline=None, excluded_kinds=())
    assert not result.errors, result.errors


class TestValidation:
    def test_valider_une_selection_vide_est_refuse(
        self, client, shared_collection, client_session
    ) -> None:
        response = client.post(VALIDATE_URL, headers=client_session["headers"])
        assert response.status_code == 409
        assert response.json()["code"] == "empty_selection"

    def test_la_validation_met_deux_travaux_en_file(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"][:2])

        response = client.post(VALIDATE_URL, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "validated"
        assert body["delivery"]["status"] == "pending"

        kinds = set(
            db_session.execute(select(Job.kind).where(Job.status == "pending")).scalars().all()
        )
        assert {"build_delivery", "refresh_draft_invoice"} <= kinds

    def test_revalider_ne_cree_pas_une_seconde_livraison(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        """Double clic, retour arrière, requête rejouée : une seule livraison, une seule
        facture. Deux livraisons pour un achat, c'est deux archives et deux factures."""
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"][:1])

        first = client.post(VALIDATE_URL, headers=headers).json()
        second = client.post(VALIDATE_URL, headers=headers).json()
        assert first["delivery"]["id"] == second["delivery"]["id"]

        deliveries = db_session.execute(select(Delivery)).scalars().all()
        assert len(deliveries) == 1

    def test_une_selection_validee_ne_bouge_plus(
        self, client, shared_collection, client_session
    ) -> None:
        headers = client_session["headers"]
        media_ids = shared_collection["media_ids"]
        _select(client, headers, media_ids[:1])
        client.post(VALIDATE_URL, headers=headers)

        added = client.put(
            f"/api/v1/public/selection/items/{media_ids[1]}", json={}, headers=headers
        )
        assert added.status_code == 409
        assert added.json()["code"] == "selection_validated"

        removed = client.delete(f"/api/v1/public/selection/items/{media_ids[0]}", headers=headers)
        assert removed.status_code == 409


class TestPreparation:
    def test_le_worker_mesure_larchive_avant_de_la_declarer_prete(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"])
        client.post(VALIDATE_URL, headers=headers)
        _drain()

        status = client.get("/api/v1/public/delivery", headers=headers).json()
        assert status["status"] == "ready"
        assert status["ready"] is True
        assert status["item_count"] == 3
        assert status["byte_size"] > 0

    def test_un_hd_manquant_fait_echouer_la_livraison_avec_un_motif(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        """Livrer une archive incomplète sans le dire serait le rejet silencieux que le
        projet s'interdit : le client paierait une sélection dont il ne recevrait qu'une
        partie."""
        from apex.models.media import Media

        headers = client_session["headers"]
        orphan = shared_collection["media_ids"][0]
        db_session.get(Media, orphan).storage_key_hd = None
        db_session.commit()

        _select(client, headers, shared_collection["media_ids"])
        client.post(VALIDATE_URL, headers=headers)
        _drain()

        delivery = db_session.execute(select(Delivery)).scalars().one()
        db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert str(orphan) in (delivery.error or "")

        # Et le studio peut lire ce motif, pas seulement un statut rouge.
        studio = client.get(
            f"/api/v1/deliveries/{delivery.id}", headers=auth_headers(shared_collection["owner"])
        )
        assert studio.status_code == 200
        assert studio.json()["error"]


class TestTelechargement:
    def test_le_hd_ne_sort_pas_avant_validation(
        self, client, shared_collection, client_session
    ) -> None:
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"][:1])
        response = client.get(ARCHIVE_URL, headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == "delivery_not_ready"

    def test_le_hd_ne_sort_pas_avant_que_larchive_soit_prete(
        self, client, shared_collection, client_session
    ) -> None:
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"][:1])
        client.post(VALIDATE_URL, headers=headers)
        # Volontairement sans drainer : la livraison est encore `pending`.
        assert client.get(ARCHIVE_URL, headers=headers).status_code == 403

    def test_larchive_est_relisible_et_nommee_lisiblement(
        self, client, shared_collection, client_session
    ) -> None:
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"])
        client.post(VALIDATE_URL, headers=headers)
        _drain()

        response = client.get(ARCHIVE_URL, headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        assert ".zip" in response.headers["content-disposition"]

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            assert len(names) == 3
            # Rang en tête pour que l'ordre chronologique survive à un tri par nom.
            assert names == sorted(names)
            assert all(name.endswith(".jpg") for name in names)
            # Le contenu est réellement là, pas seulement l'entrée.
            assert len(archive.read(names[0])) > 0

    def test_la_taille_annoncee_est_la_taille_reelle(
        self, client, shared_collection, client_session
    ) -> None:
        """`Content-Length` exact : c'est ce qui donne une vraie barre de progression, et
        c'est ce que `ZIP_STORED` permet de calculer avant d'avoir produit un octet."""
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"])
        client.post(VALIDATE_URL, headers=headers)
        _drain()

        response = client.get(ARCHIVE_URL, headers=headers)
        assert int(response.headers["content-length"]) == len(response.content)


class TestFactureBrouillon:
    def test_la_validation_produit_une_facture_brouillon_chiffree(
        self, client, shared_collection, client_session, db_session
    ) -> None:
        headers = client_session["headers"]
        _select(client, headers, shared_collection["media_ids"][:2])
        client.post(VALIDATE_URL, headers=headers)
        _drain()

        invoice = db_session.execute(select(Invoice)).scalars().one()
        lines = (
            db_session.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
            .scalars()
            .all()
        )
        assert invoice.status == "draft"
        assert invoice.number is None, "une facture brouillon n'a pas de numéro"
        assert len(lines) == 1
        assert lines[0].quantity == 2
        assert invoice.subtotal_cents == lines[0].amount_cents
        # TVA appliquée sur le sous-total, arrondie au centime.
        assert invoice.total_cents == round(invoice.subtotal_cents * (1 + float(invoice.vat_rate)))
