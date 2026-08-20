"""Facturation et devis (J3, §3-O). Immuabilité de la facture émise garantie par trigger
PL/pgSQL — `PATCH /invoices/{id}` est refusé (`409 invoice_issued`) hors `draft`.
"""

from fastapi import APIRouter, Query, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.billing import (
    InvoiceFromSelectionRequest,
    InvoiceOut,
    InvoicePatchRequest,
    QuoteAcceptResponse,
    QuoteCreateRequest,
    QuoteOut,
)
from apex.schemas.common import Page

router = APIRouter(tags=["billing"], dependencies=[Security(bearer_scheme)])


@router.post(
    "/invoices/from-selection/{selection_id}",
    response_model=InvoiceOut,
    status_code=201,
    summary="Créer une facture brouillon depuis une sélection validée",
)
def create_invoice_from_selection(
    selection_id: int, payload: InvoiceFromSelectionRequest
) -> InvoiceOut:
    not_implemented("POST /invoices/from-selection/{selection_id}")


@router.get("/invoices", response_model=Page[InvoiceOut], summary="Liste des factures")
def list_invoices(
    client_id: int | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[InvoiceOut]:
    not_implemented("GET /invoices")


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut, summary="Détail facture + lignes")
def get_invoice(invoice_id: int) -> InvoiceOut:
    not_implemented("GET /invoices/{id}")


@router.patch(
    "/invoices/{invoice_id}",
    response_model=InvoiceOut,
    summary="Modifier lignes/TVA — `draft` uniquement, `409 invoice_issued` sinon",
)
def patch_invoice(invoice_id: int, payload: InvoicePatchRequest) -> InvoiceOut:
    not_implemented("PATCH /invoices/{id}")


@router.post(
    "/invoices/{invoice_id}/issue", response_model=InvoiceOut, summary="Émettre la facture"
)
def issue_invoice(invoice_id: int) -> InvoiceOut:
    not_implemented("POST /invoices/{id}/issue")


@router.get("/quotes", response_model=Page[QuoteOut], summary="Liste des devis")
def list_quotes(
    cursor: str | None = None, limit: int = Query(default=50, le=100)
) -> Page[QuoteOut]:
    not_implemented("GET /quotes")


@router.post("/quotes", response_model=QuoteOut, status_code=201, summary="Créer un devis")
def create_quote(payload: QuoteCreateRequest) -> QuoteOut:
    not_implemented("POST /quotes")


@router.get("/quotes/{quote_id}", response_model=QuoteOut, summary="Détail devis")
def get_quote(quote_id: int) -> QuoteOut:
    not_implemented("GET /quotes/{id}")


@router.post(
    "/quotes/{quote_id}/accept",
    response_model=QuoteAcceptResponse,
    summary="Accepter le devis — crée le shooting correspondant",
)
def accept_quote(quote_id: int) -> QuoteAcceptResponse:
    not_implemented("POST /quotes/{id}/accept")
