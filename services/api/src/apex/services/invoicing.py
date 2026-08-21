"""Composition d'une facture à partir d'une sélection validée (§3-O du plan).

Deux règles, et la seconde est l'invariant métier le plus fort du projet :

1. Une facture **brouillon** se recompose à chaque changement de la sélection validée.
2. Une facture **émise** ne bouge plus jamais. Ses lignes sont un *snapshot* — libellé,
   quantité, prix unitaire — sans clé étrangère vivante vers `media` : si les lignes
   pointaient les médias, le contenu d'une facture déjà envoyée changerait dès qu'une
   sélection bouge. La garantie finale est un trigger PL/pgSQL, pas ce module : une garde
   applicative tient jusqu'à la première route qui l'oublie.

Le prix unitaire vit dans `app_setting`, jamais dans le code : un tarif est une décision
commerciale, elle ne devrait pas demander un déploiement.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from apex.models.billing import ClientSelection, Invoice, InvoiceLine, SelectionItem
from apex.models.collection import Collection
from apex.services.app_settings import get_setting

PHOTO_UNIT_PRICE_KEY = "photo_unit_price_cents"
PHOTO_UNIT_PRICE_DEFAULT = 1500
VAT_RATE_KEY = "default_vat_rate"
VAT_RATE_DEFAULT = 0.20

#: Libellé de la seule prestation facturée à ce stade. Le plan prévoit un regroupement
#: « par type de prestation » ; il n'en existe qu'un tant que le studio ne vend que de la
#: photo livrée à l'unité. Le jour où un second type apparaît (retouche, tirage), c'est
#: cette fonction qui produit deux lignes, pas l'appelant.
PHOTO_LINE_LABEL = "Photographies haute définition livrées"


def get_photo_unit_price_cents(session: Session) -> int:
    return int(get_setting(session, PHOTO_UNIT_PRICE_KEY, PHOTO_UNIT_PRICE_DEFAULT))


def get_default_vat_rate(session: Session) -> float:
    return float(get_setting(session, VAT_RATE_KEY, VAT_RATE_DEFAULT))


def compute_totals(lines: list[InvoiceLine], vat_rate: float) -> tuple[int, int]:
    """`(subtotal_cents, total_cents)`.

    Arrondi en `Decimal` au centime le plus proche, jamais en flottant : `0.1 + 0.2` sur un
    total de facture finit par produire un centime d'écart que personne ne sait expliquer.
    """
    subtotal = sum(line.amount_cents for line in lines)
    total = Decimal(subtotal) * (Decimal("1") + Decimal(str(vat_rate)))
    return subtotal, int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_photo_line(quantity: int, unit_price_cents: int) -> InvoiceLine:
    return InvoiceLine(
        label=PHOTO_LINE_LABEL,
        quantity=quantity,
        unit_price_cents=unit_price_cents,
        amount_cents=quantity * unit_price_cents,
        position=0,
    )


def refresh_draft_invoice(session: Session, selection_id: int) -> Invoice | None:
    """Crée ou met à jour la facture **brouillon** d'une sélection validée.

    Renvoie `None` si la sélection n'est pas validée : une sélection en cours n'a pas à
    produire de facture, même brouillon — le studio verrait un montant bouger à chaque clic
    du client. Ne touche jamais une facture émise : elle est figée, et le trigger le
    garantirait de toute façon.
    """
    selection = session.get(ClientSelection, selection_id)
    if selection is None or selection.status != "validated":
        return None

    collection = session.get(Collection, selection.collection_id)
    if collection is None:
        return None

    invoice = session.execute(
        select(Invoice).where(Invoice.selection_id == selection.id)
    ).scalar_one_or_none()
    if invoice is not None and invoice.status == "issued":
        return invoice

    quantity = int(
        session.execute(
            select(func.count())
            .select_from(SelectionItem)
            .where(SelectionItem.selection_id == selection.id)
        ).scalar_one()
    )
    unit_price = get_photo_unit_price_cents(session)

    if invoice is None:
        invoice = Invoice(
            client_id=collection.client_id,
            collection_id=collection.id,
            selection_id=selection.id,
            status="draft",
            vat_rate=get_default_vat_rate(session),
        )
        session.add(invoice)
        session.flush()
    else:
        session.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))

    line = build_photo_line(quantity, unit_price)
    line.invoice_id = invoice.id
    session.add(line)
    session.flush()

    invoice.subtotal_cents, invoice.total_cents = compute_totals([line], float(invoice.vat_rate))
    session.flush()
    return invoice
