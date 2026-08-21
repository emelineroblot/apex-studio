/** Facturation, devis, partage et tableau de bord (J3, côté studio — JWT interne). */
import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/billing";
import type {
  DashboardOut,
  DeliveryOut,
  InvoiceOut,
  InvoicePatchRequest,
  Page,
  QuoteAcceptResponse,
  QuoteCreateRequest,
  QuoteOut,
  SelectionOut,
  ShareLinkCreateResponse,
  ShareLinkOut,
} from "@/lib/api/types";

// ── Partage ───────────────────────────────────────────────────────────────────────────

/** `POST /collections/{id}/share-links` — **le `token` en clair n'est renvoyé qu'ici**. */
export async function createShareLink(
  collectionId: number,
  expiresInDays: number,
): Promise<ShareLinkCreateResponse> {
  if (API_MODE === "fixtures") return fixtures.createShareLink(collectionId, expiresInDays);
  return apiRequest<ShareLinkCreateResponse>(`/collections/${collectionId}/share-links`, {
    method: "POST",
    json: { expires_in_days: expiresInDays },
  });
}

export async function listShareLinks(collectionId: number): Promise<ShareLinkOut[]> {
  if (API_MODE === "fixtures") return fixtures.listShareLinks(collectionId);
  return apiRequest<ShareLinkOut[]>(`/collections/${collectionId}/share-links`);
}

export async function revokeShareLink(id: string): Promise<void> {
  if (API_MODE === "fixtures") return fixtures.revokeShareLink(id);
  await apiRequest<void>(`/share-links/${id}`, { method: "DELETE" });
}

export async function getCollectionSelection(collectionId: number): Promise<SelectionOut> {
  if (API_MODE === "fixtures") return fixtures.getCollectionSelection(collectionId);
  return apiRequest<SelectionOut>(`/collections/${collectionId}/selection`);
}

export async function getDelivery(id: number): Promise<DeliveryOut> {
  if (API_MODE === "fixtures") return fixtures.getDelivery(id);
  return apiRequest<DeliveryOut>(`/deliveries/${id}`);
}

// ── Factures ──────────────────────────────────────────────────────────────────────────

export async function listInvoices(
  params: { client_id?: number | null; status?: string | null; cursor?: string | null; limit?: number } = {},
): Promise<Page<InvoiceOut>> {
  if (API_MODE === "fixtures") return fixtures.listInvoices(params);
  return apiRequest<Page<InvoiceOut>>("/invoices", { query: { ...params } });
}

export async function getInvoice(id: number): Promise<InvoiceOut> {
  if (API_MODE === "fixtures") return fixtures.getInvoice(id);
  return apiRequest<InvoiceOut>(`/invoices/${id}`);
}

export async function createInvoiceFromSelection(
  selectionId: number,
  vatRate?: number | null,
): Promise<InvoiceOut> {
  if (API_MODE === "fixtures") return fixtures.createInvoiceFromSelection(selectionId, vatRate);
  return apiRequest<InvoiceOut>(`/invoices/from-selection/${selectionId}`, {
    method: "POST",
    json: { vat_rate: vatRate ?? null },
  });
}

/** Refusé (`409 invoice_issued`) dès que la facture est émise — l'UI désactive avant. */
export async function patchInvoice(id: number, payload: InvoicePatchRequest): Promise<InvoiceOut> {
  if (API_MODE === "fixtures") return fixtures.patchInvoice(id, payload);
  return apiRequest<InvoiceOut>(`/invoices/${id}`, { method: "PATCH", json: payload });
}

export async function issueInvoice(id: number): Promise<InvoiceOut> {
  if (API_MODE === "fixtures") return fixtures.issueInvoice(id);
  return apiRequest<InvoiceOut>(`/invoices/${id}/issue`, { method: "POST" });
}

// ── Devis ─────────────────────────────────────────────────────────────────────────────

export async function listQuotes(
  params: { cursor?: string | null; limit?: number } = {},
): Promise<Page<QuoteOut>> {
  if (API_MODE === "fixtures") return fixtures.listQuotes(params);
  return apiRequest<Page<QuoteOut>>("/quotes", { query: { ...params } });
}

export async function createQuote(payload: QuoteCreateRequest): Promise<QuoteOut> {
  if (API_MODE === "fixtures") return fixtures.createQuote(payload);
  return apiRequest<QuoteOut>("/quotes", { method: "POST", json: payload });
}

export async function acceptQuote(id: number): Promise<QuoteAcceptResponse> {
  if (API_MODE === "fixtures") return fixtures.acceptQuote(id);
  return apiRequest<QuoteAcceptResponse>(`/quotes/${id}/accept`, { method: "POST" });
}

// ── Tableau de bord ───────────────────────────────────────────────────────────────────

export async function dashboard(
  params: { from?: string | null; to?: string | null } = {},
): Promise<DashboardOut> {
  if (API_MODE === "fixtures") return fixtures.dashboard(params);
  return apiRequest<DashboardOut>("/dashboard", { query: { from: params.from, to: params.to } });
}
