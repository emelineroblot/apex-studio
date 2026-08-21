"""Immuabilité de la facture émise (§3-O) — l'invariant métier le plus fort du projet.

Il est tenu à trois niveaux. Ces tests vérifient les trois, dans l'ordre où ils cèdent :
la route refuse, le modèle contraint, et le trigger PL/pgSQL lève. Le troisième est le
seul qui survive à une route écrite trop vite ou à une correction faite à la main en base
— c'est donc lui qu'il faut prouver, pas seulement le `409`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from apex.models.billing import ClientSelection, Invoice, InvoiceLine, SelectionItem
from apex.models.collection import Collection, CollectionItem
from apex.services import invoicing
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
def validated_selection(db_session: Session) -> dict:
    from datetime import UTC, datetime

    owner = make_user(db_session, role="owner", email="owner-billing@apex-test.dev")
    photographer = make_user(
        db_session, role="photographer", email="photographer-billing@apex-test.dev"
    )
    circuit = make_circuit(db_session, "Circuit Facturation")
    demo_client = make_client(db_session, "Client Facturation")
    camera = make_camera(db_session)
    base = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
    batch = make_upload_batch(db_session, user=owner)

    collection = Collection(
        client_id=demo_client.id,
        shooting_id=shooting.id,
        title="Facturation GP",
        status="published",
        created_by=owner.id,
    )
    db_session.add(collection)
    db_session.flush()
    selection = ClientSelection(collection_id=collection.id, status="validated")
    db_session.add(selection)
    db_session.flush()

    for _ in range(4):
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            camera=camera,
            shot_at=base,
            attachment_status="shooting_attached",
            attachment_source="pipeline_time",
        )
        db_session.add(CollectionItem(collection_id=collection.id, media_id=media.id))
        db_session.add(SelectionItem(selection_id=selection.id, media_id=media.id))
    db_session.commit()

    invoice = invoicing.refresh_draft_invoice(db_session, selection.id)
    db_session.commit()
    return {
        "owner": owner,
        "photographer": photographer,
        "client_id": demo_client.id,
        "circuit_id": circuit.id,
        "selection_id": selection.id,
        "invoice_id": invoice.id,
    }


class TestBrouillon:
    def test_une_facture_brouillon_na_pas_de_numero(self, client, validated_selection) -> None:
        """Un numéro attribué puis abandonné laisse un trou dans une séquence comptable."""
        response = client.get(
            f"/api/v1/invoices/{validated_selection['invoice_id']}",
            headers=auth_headers(validated_selection["owner"]),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "draft"
        assert body["number"] is None
        assert body["lines"][0]["quantity"] == 4

    def test_une_facture_brouillon_suit_la_selection(
        self, client, validated_selection, db_session
    ) -> None:
        db_session.execute(
            text(
                "DELETE FROM selection_item WHERE selection_id = :sid AND media_id = ("
                "SELECT min(media_id) FROM selection_item WHERE selection_id = :sid)"
            ),
            {"sid": validated_selection["selection_id"]},
        )
        db_session.commit()

        invoicing.refresh_draft_invoice(db_session, validated_selection["selection_id"])
        db_session.commit()

        invoice = db_session.get(Invoice, validated_selection["invoice_id"])
        db_session.refresh(invoice)
        lines = db_session.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).all()
        assert len(lines) == 1, "la recomposition remplace les lignes, elle ne les empile pas"
        assert lines[0].quantity == 3

    def test_les_lignes_modifiees_recalculent_le_total(self, client, validated_selection) -> None:
        response = client.patch(
            f"/api/v1/invoices/{validated_selection['invoice_id']}",
            json={
                "lines": [
                    {"label": "Reportage", "quantity": 2, "unit_price_cents": 25000, "position": 0}
                ],
                "vat_rate": 0.2,
            },
            headers=auth_headers(validated_selection["owner"]),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["subtotal_cents"] == 50000
        assert body["total_cents"] == 60000
        # Le montant de ligne est calculé, jamais accepté depuis la requête.
        assert body["lines"][0]["amount_cents"] == 50000


class TestEmission:
    def test_lemission_attribue_un_numero_et_une_date(self, client, validated_selection) -> None:
        response = client.post(
            f"/api/v1/invoices/{validated_selection['invoice_id']}/issue",
            headers=auth_headers(validated_selection["owner"]),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "issued"
        assert body["number"] is not None
        assert body["issued_at"] is not None

    def test_reemettre_ne_consomme_pas_un_second_numero(self, client, validated_selection) -> None:
        url = f"/api/v1/invoices/{validated_selection['invoice_id']}/issue"
        headers = auth_headers(validated_selection["owner"])
        first = client.post(url, headers=headers).json()
        second = client.post(url, headers=headers).json()
        assert first["number"] == second["number"]

    def test_une_facture_emise_refuse_toute_modification(self, client, validated_selection) -> None:
        headers = auth_headers(validated_selection["owner"])
        client.post(f"/api/v1/invoices/{validated_selection['invoice_id']}/issue", headers=headers)

        response = client.patch(
            f"/api/v1/invoices/{validated_selection['invoice_id']}",
            json={"vat_rate": 0.1},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["code"] == "invoice_issued"


class TestTriggerPostgres:
    """La garantie finale — celle qui ne dépend pas de la discipline du code applicatif."""

    def test_le_trigger_refuse_de_modifier_une_ligne_de_facture_emise(
        self, client, validated_selection, db_session
    ) -> None:
        headers = auth_headers(validated_selection["owner"])
        client.post(f"/api/v1/invoices/{validated_selection['invoice_id']}/issue", headers=headers)
        db_session.commit()

        with pytest.raises(DatabaseError):
            db_session.execute(
                text("UPDATE invoice_line SET quantity = 999 WHERE invoice_id = :id"),
                {"id": validated_selection["invoice_id"]},
            )
            db_session.commit()
        db_session.rollback()

    def test_le_trigger_refuse_de_supprimer_une_ligne_de_facture_emise(
        self, client, validated_selection, db_session
    ) -> None:
        headers = auth_headers(validated_selection["owner"])
        client.post(f"/api/v1/invoices/{validated_selection['invoice_id']}/issue", headers=headers)
        db_session.commit()

        with pytest.raises(DatabaseError):
            db_session.execute(
                text("DELETE FROM invoice_line WHERE invoice_id = :id"),
                {"id": validated_selection["invoice_id"]},
            )
            db_session.commit()
        db_session.rollback()

    def test_le_trigger_refuse_le_retour_de_emise_a_brouillon(
        self, client, validated_selection, db_session
    ) -> None:
        """Repasser une facture en brouillon rouvrirait la porte à toutes les autres
        modifications : c'est le contournement le plus évident, il est fermé en base."""
        headers = auth_headers(validated_selection["owner"])
        client.post(f"/api/v1/invoices/{validated_selection['invoice_id']}/issue", headers=headers)
        db_session.commit()

        with pytest.raises(DatabaseError):
            db_session.execute(
                text("UPDATE invoice SET status = 'draft' WHERE id = :id"),
                {"id": validated_selection["invoice_id"]},
            )
            db_session.commit()
        db_session.rollback()

    def test_une_facture_brouillon_reste_modifiable_en_base(
        self, validated_selection, db_session
    ) -> None:
        """Contre-épreuve : le trigger ne verrouille que l'émis. Sans ce test, un trigger
        qui bloquerait *tout* passerait les trois précédents."""
        db_session.execute(
            text("UPDATE invoice_line SET quantity = 2 WHERE invoice_id = :id"),
            {"id": validated_selection["invoice_id"]},
        )
        db_session.commit()
        line = (
            db_session.query(InvoiceLine)
            .filter(InvoiceLine.invoice_id == validated_selection["invoice_id"])
            .first()
        )
        assert float(line.quantity) == 2.0


class TestCloisonnement:
    def test_un_photographe_ne_voit_pas_la_facturation(self, client, validated_selection) -> None:
        headers = auth_headers(validated_selection["photographer"])
        assert client.get("/api/v1/invoices", headers=headers).status_code == 403
        assert (
            client.get(
                f"/api/v1/invoices/{validated_selection['invoice_id']}", headers=headers
            ).status_code
            == 403
        )
