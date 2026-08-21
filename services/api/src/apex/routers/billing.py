"""Facturation et devis (J3, §3-O).

L'invariant le plus fort du projet vit ici : **une facture émise est immuable**. Il est
tenu à trois niveaux, du plus faible au plus solide — cette route refuse (`409`), le
modèle contraint (`CHECK`), et un trigger PL/pgSQL lève. Les deux premiers documentent
l'intention ; le troisième est celui qui survit à une route écrite trop vite, à un script
de maintenance ou à une correction faite à la main en base.

Le numéro de facture est consommé sur `invoice_number_seq` **à l'émission seulement** :
une facture brouillon n'a pas de numéro, parce qu'un numéro attribué puis abandonné laisse
un trou dans une séquence comptable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.billing import ClientSelection, Invoice, InvoiceLine, Quote
from apex.models.catalog import Circuit, Client
from apex.models.shooting import Shooting
from apex.routers._common import bearer_scheme
from apex.schemas.billing import (
    CreatedShootingRef,
    InvoiceFromSelectionRequest,
    InvoiceLineOut,
    InvoiceOut,
    InvoicePatchRequest,
    InvoiceStatus,
    QuoteAcceptResponse,
    QuoteCreateRequest,
    QuoteOut,
)
from apex.schemas.common import Page
from apex.security import CurrentUser
from apex.services import access, invoicing
from apex.services.pagination import paginate_by_id

router = APIRouter(tags=["billing"], dependencies=[Security(bearer_scheme)])

#: Format du numéro : `AAAA-NNNN`. L'année en tête pour que le tri chronologique soit le
#: tri naturel, et parce qu'une séquence comptable se lit par exercice.
INVOICE_NUMBER_FORMAT = "{year}-{sequence:04d}"


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "not_found", "message": f"{what} introuvable.", "detail": None},
    )


def _invoice_issued() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "invoice_issued",
            "message": "Cette facture est émise : elle ne peut plus être modifiée.",
            "detail": None,
        },
    )


def _lines(db: Session, invoice_id: int) -> list[InvoiceLine]:
    return list(
        db.execute(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice_id)
            .order_by(InvoiceLine.position, InvoiceLine.id)
        )
        .scalars()
        .all()
    )


def _invoice_out(db: Session, invoice: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id,
        client_id=invoice.client_id,
        collection_id=invoice.collection_id,
        selection_id=invoice.selection_id,
        number=invoice.number,
        status=cast(InvoiceStatus, invoice.status),
        issued_at=invoice.issued_at,
        subtotal_cents=invoice.subtotal_cents,
        vat_rate=float(invoice.vat_rate),
        total_cents=invoice.total_cents,
        lines=[InvoiceLineOut.model_validate(line) for line in _lines(db, invoice.id)],
    )


def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise _not_found("Facture")
    return invoice


@router.post(
    "/invoices/from-selection/{selection_id}",
    response_model=InvoiceOut,
    status_code=201,
    summary="Créer une facture brouillon depuis une sélection validée",
)
def create_invoice_from_selection(
    selection_id: int,
    payload: InvoiceFromSelectionRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> InvoiceOut:
    """Même composition que le handler `refresh_draft_invoice`, déclenchée à la main.

    Utile quand le studio veut la facture avant que le worker ne soit passé, ou après
    avoir ajusté un tarif. Le travail réel vit dans `services/invoicing.py` : une seule
    façon de composer une facture, quel que soit le point d'entrée.
    """
    access.require_owner(user, message="Seul le dirigeant peut facturer.")
    selection = db.get(ClientSelection, selection_id)
    if selection is None:
        raise _not_found("Sélection")
    if selection.status != "validated":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "selection_not_validated",
                "message": "La sélection du client n'est pas encore validée.",
                "detail": None,
            },
        )

    invoice = invoicing.refresh_draft_invoice(db, selection_id)
    if invoice is None:
        raise _not_found("Collection de la sélection")
    if payload.vat_rate is not None and invoice.status == "draft":
        invoice.vat_rate = payload.vat_rate
        invoice.subtotal_cents, invoice.total_cents = invoicing.compute_totals(
            _lines(db, invoice.id), payload.vat_rate
        )
    db.commit()
    db.refresh(invoice)
    return _invoice_out(db, invoice)


@router.get("/invoices", response_model=Page[InvoiceOut], summary="Liste des factures")
def list_invoices(
    user: CurrentUser,
    client_id: int | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db),
) -> Page[InvoiceOut]:
    access.require_owner(user, message="Seul le dirigeant accède à la facturation.")
    stmt = select(Invoice)
    if client_id is not None:
        stmt = stmt.where(Invoice.client_id == client_id)
    if status is not None:
        stmt = stmt.where(Invoice.status == status)

    items, next_cursor, total = paginate_by_id(
        db, stmt, Invoice.id, cursor=cursor, limit=limit, with_total=True
    )
    return Page(
        items=[_invoice_out(db, invoice) for invoice in items],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut, summary="Détail facture + lignes")
def get_invoice(invoice_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> InvoiceOut:
    access.require_owner(user, message="Seul le dirigeant accède à la facturation.")
    return _invoice_out(db, _get_invoice_or_404(db, invoice_id))


@router.patch(
    "/invoices/{invoice_id}",
    response_model=InvoiceOut,
    summary="Modifier lignes/TVA — `draft` uniquement, `409 invoice_issued` sinon",
)
def patch_invoice(
    invoice_id: int, payload: InvoicePatchRequest, user: CurrentUser, db: Session = Depends(get_db)
) -> InvoiceOut:
    access.require_owner(user, message="Seul le dirigeant peut modifier une facture.")
    invoice = _get_invoice_or_404(db, invoice_id)
    if invoice.status != "draft":
        raise _invoice_issued()

    if payload.lines is not None:
        for line in _lines(db, invoice.id):
            db.delete(line)
        db.flush()
        for position, incoming in enumerate(payload.lines):
            db.add(
                InvoiceLine(
                    invoice_id=invoice.id,
                    label=incoming.label,
                    quantity=incoming.quantity,
                    unit_price_cents=incoming.unit_price_cents,
                    # Le montant est **calculé**, jamais accepté depuis la requête : une
                    # ligne dont le total ne correspond pas à quantité × prix unitaire est
                    # un document comptable faux.
                    amount_cents=round(incoming.quantity * incoming.unit_price_cents),
                    position=incoming.position or position,
                )
            )
        db.flush()

    if payload.vat_rate is not None:
        invoice.vat_rate = payload.vat_rate

    invoice.subtotal_cents, invoice.total_cents = invoicing.compute_totals(
        _lines(db, invoice.id), float(invoice.vat_rate)
    )
    db.commit()
    db.refresh(invoice)
    return _invoice_out(db, invoice)


@router.post(
    "/invoices/{invoice_id}/issue", response_model=InvoiceOut, summary="Émettre la facture"
)
def issue_invoice(invoice_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> InvoiceOut:
    access.require_owner(user, message="Seul le dirigeant peut émettre une facture.")
    invoice = _get_invoice_or_404(db, invoice_id)
    if invoice.status == "issued":
        # Idempotent : réémettre une facture déjà émise la renvoie telle quelle. Consommer
        # un second numéro pour le même document créerait un trou dans la séquence.
        return _invoice_out(db, invoice)
    if not _lines(db, invoice.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "empty_invoice",
                "message": "Une facture sans ligne ne peut pas être émise.",
                "detail": None,
            },
        )

    now = datetime.now(UTC)
    sequence = int(db.execute(text("SELECT nextval('invoice_number_seq')")).scalar_one())
    invoice.number = INVOICE_NUMBER_FORMAT.format(year=now.year, sequence=sequence)
    invoice.issued_at = now
    invoice.status = "issued"
    db.commit()
    db.refresh(invoice)
    return _invoice_out(db, invoice)


# --- Devis ----------------------------------------------------------------------------


@router.get("/quotes", response_model=Page[QuoteOut], summary="Liste des devis")
def list_quotes(
    user: CurrentUser,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db),
) -> Page[QuoteOut]:
    items, next_cursor, total = paginate_by_id(
        db, select(Quote), Quote.id, cursor=cursor, limit=limit, with_total=True
    )
    return Page(
        items=[QuoteOut.model_validate(quote) for quote in items],
        next_cursor=next_cursor,
        total=total,
    )


@router.post("/quotes", response_model=QuoteOut, status_code=201, summary="Créer un devis")
def create_quote(
    payload: QuoteCreateRequest, user: CurrentUser, db: Session = Depends(get_db)
) -> QuoteOut:
    access.require_owner(user, message="Seul le dirigeant peut établir un devis.")
    if db.get(Client, payload.client_id) is None:
        raise _not_found("Client")
    if db.get(Circuit, payload.circuit_id) is None:
        raise _not_found("Circuit")
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_period",
                "message": "La fin doit être postérieure au début.",
                "detail": None,
            },
        )

    quote = Quote(
        client_id=payload.client_id,
        circuit_id=payload.circuit_id,
        title=payload.title,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        amount_cents=payload.amount_cents,
        status="draft",
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return QuoteOut.model_validate(quote)


@router.get("/quotes/{quote_id}", response_model=QuoteOut, summary="Détail devis")
def get_quote(quote_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> QuoteOut:
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise _not_found("Devis")
    return QuoteOut.model_validate(quote)


@router.post(
    "/quotes/{quote_id}/accept",
    response_model=QuoteAcceptResponse,
    summary="Accepter le devis — crée le shooting correspondant",
)
def accept_quote(
    quote_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> QuoteAcceptResponse:
    """Accepter, c'est **créer le shooting**, dans la même transaction.

    C'est tout l'intérêt métier de la route : la période et le client du devis deviennent
    la fenêtre temporelle qui rattachera automatiquement les photos (§3-F.3). Un devis
    accepté sans shooting obligerait à ressaisir les mêmes dates, avec le risque qu'elles
    diffèrent d'une minute — et un décalage d'une minute, ici, ce sont des photos qui ne
    se rattachent pas.
    """
    access.require_owner(user, message="Seul le dirigeant peut accepter un devis.")
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise _not_found("Devis")

    if quote.status == "accepted" and quote.created_shooting_id is not None:
        # Idempotent : deux acceptations ne créent pas deux shootings, sans quoi les
        # photos se rattacheraient à l'un ou à l'autre selon l'ordre des identifiants.
        shooting = db.get(Shooting, quote.created_shooting_id)
        if shooting is not None:
            return QuoteAcceptResponse(
                quote=QuoteOut.model_validate(quote),
                created_shooting=CreatedShootingRef(id=shooting.id, title=shooting.title),
            )

    if quote.status == "refused":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "quote_refused",
                "message": "Ce devis a été refusé : il ne peut plus être accepté.",
                "detail": None,
            },
        )

    shooting = Shooting(
        client_id=quote.client_id,
        circuit_id=quote.circuit_id,
        title=quote.title,
        starts_at=quote.starts_at,
        ends_at=quote.ends_at,
        status="planned",
    )
    db.add(shooting)
    db.flush()

    quote.status = "accepted"
    quote.accepted_at = datetime.now(UTC)
    quote.created_shooting_id = shooting.id
    db.commit()
    db.refresh(quote)
    return QuoteAcceptResponse(
        quote=QuoteOut.model_validate(quote),
        created_shooting=CreatedShootingRef(id=shooting.id, title=shooting.title),
    )
