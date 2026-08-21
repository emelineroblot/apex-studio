/**
 * Facturation, devis, partage et tableau de bord en mode "fixtures".
 *
 * Rejoue les deux règles que les écrans doivent savoir afficher : une facture émise ne
 * bouge plus, et le jeton d'un lien de partage n'apparaît qu'à sa création. Un mode
 * fixtures qui laisserait modifier une facture émise validerait une interface qui ne
 * désactive pas ses champs — le `409` du backend arriverait alors en production.
 */
import { ApiError } from "@/lib/api/errors";
import { delay, nextId, notFound, paginate } from "@/lib/api/fixtures/utils";
import { clients, collections } from "@/lib/api/fixtures/db";
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

const MASKED_URL = `http://localhost:3000/c/${"•".repeat(43)}`;

type FixtureShareLink = ShareLinkOut & { collection_id: number };

const shareLinks: FixtureShareLink[] = [];

const invoices: InvoiceOut[] = [
  {
    id: 9001,
    client_id: clients[0]?.id ?? 1,
    collection_id: collections[0]?.id ?? 1,
    selection_id: 7001,
    number: "2026-0007",
    status: "issued",
    issued_at: new Date(Date.UTC(2026, 3, 28, 9, 30)).toISOString(),
    subtotal_cents: 96000,
    vat_rate: 0.2,
    total_cents: 115200,
    lines: [
      {
        label: "Photographies haute définition livrées",
        quantity: 64,
        unit_price_cents: 1500,
        amount_cents: 96000,
        position: 0,
      },
    ],
  },
  {
    id: 9002,
    client_id: clients[1]?.id ?? 2,
    collection_id: collections[0]?.id ?? 1,
    selection_id: 7002,
    number: null,
    status: "draft",
    issued_at: null,
    subtotal_cents: 27000,
    vat_rate: 0.2,
    total_cents: 32400,
    lines: [
      {
        label: "Photographies haute définition livrées",
        quantity: 18,
        unit_price_cents: 1500,
        amount_cents: 27000,
        position: 0,
      },
    ],
  },
];

const quotes: QuoteOut[] = [
  {
    id: 8001,
    client_id: clients[0]?.id ?? 1,
    circuit_id: 1,
    title: "Week-end GT — Magny-Cours",
    starts_at: new Date(Date.UTC(2026, 8, 12, 8, 0)).toISOString(),
    ends_at: new Date(Date.UTC(2026, 8, 13, 18, 0)).toISOString(),
    amount_cents: 180000,
    status: "draft",
    accepted_at: null,
    created_shooting_id: null,
  },
];

function issuedGuard(invoice: InvoiceOut): void {
  if (invoice.status === "issued") {
    throw new ApiError(409, {
      code: "invoice_issued",
      message: "Cette facture est émise : elle ne peut plus être modifiée.",
    });
  }
}

function recompute(invoice: InvoiceOut): InvoiceOut {
  const subtotal = invoice.lines.reduce((sum, line) => sum + line.amount_cents, 0);
  invoice.subtotal_cents = subtotal;
  invoice.total_cents = Math.round(subtotal * (1 + invoice.vat_rate));
  return invoice;
}

// ── Partage ───────────────────────────────────────────────────────────────────────────

export async function createShareLink(
  collectionId: number,
  expiresInDays: number,
): Promise<ShareLinkCreateResponse> {
  await delay(280);
  const id = `fixture-${nextId()}`;
  const expiresAt = new Date(Date.now() + expiresInDays * 86_400_000).toISOString();
  shareLinks.unshift({
    id,
    collection_id: collectionId,
    url_masked: MASKED_URL,
    expires_at: expiresAt,
    revoked_at: null,
    view_count: 0,
    last_seen_at: null,
  });
  // « demo » est le jeton que reconnaît l'espace client en fixtures : le lien copié depuis
  // cet écran est réellement ouvrable, ce qui rend la démonstration jouable de bout en bout.
  return {
    id,
    url: "http://localhost:3000/c/demo",
    token: "demo",
    expires_at: expiresAt,
  };
}

export async function listShareLinks(collectionId: number): Promise<ShareLinkOut[]> {
  await delay(180);
  return shareLinks
    .filter((link) => link.collection_id === collectionId)
    .map(({ collection_id: _ignored, ...link }) => link);
}

export async function revokeShareLink(id: string): Promise<void> {
  await delay(180);
  const link = shareLinks.find((entry) => entry.id === id);
  if (!link) notFound("Lien");
  link.revoked_at = link.revoked_at ?? new Date().toISOString();
}

export async function getCollectionSelection(_collectionId: number): Promise<SelectionOut> {
  await delay(200);
  return {
    status: "open",
    validated_at: null,
    items: [],
    count: 0,
  };
}

export async function getDelivery(_id: number): Promise<DeliveryOut> {
  await delay(200);
  return {
    status: "ready",
    item_count: 18,
    byte_size: 151_000_000,
    built_at: new Date().toISOString(),
    error: null,
  };
}

// ── Factures ──────────────────────────────────────────────────────────────────────────

export async function listInvoices(
  params: { client_id?: number | null; status?: string | null; cursor?: string | null; limit?: number } = {},
): Promise<Page<InvoiceOut>> {
  await delay(220);
  const filtered = invoices.filter(
    (invoice) =>
      (!params.client_id || invoice.client_id === params.client_id) &&
      (!params.status || invoice.status === params.status),
  );
  return paginate([...filtered].sort((a, b) => b.id - a.id), params.cursor, params.limit ?? 50);
}

export async function getInvoice(id: number): Promise<InvoiceOut> {
  await delay(180);
  const invoice = invoices.find((entry) => entry.id === id);
  if (!invoice) notFound("Facture");
  return structuredClone(invoice);
}

export async function createInvoiceFromSelection(
  selectionId: number,
  vatRate?: number | null,
): Promise<InvoiceOut> {
  await delay(300);
  const created: InvoiceOut = {
    id: nextId(),
    client_id: clients[0]?.id ?? 1,
    collection_id: collections[0]?.id ?? 1,
    selection_id: selectionId,
    number: null,
    status: "draft",
    issued_at: null,
    subtotal_cents: 0,
    vat_rate: vatRate ?? 0.2,
    total_cents: 0,
    lines: [
      {
        label: "Photographies haute définition livrées",
        quantity: 12,
        unit_price_cents: 1500,
        amount_cents: 18000,
        position: 0,
      },
    ],
  };
  invoices.push(recompute(created));
  return structuredClone(created);
}

export async function patchInvoice(id: number, payload: InvoicePatchRequest): Promise<InvoiceOut> {
  await delay(260);
  const invoice = invoices.find((entry) => entry.id === id);
  if (!invoice) notFound("Facture");
  issuedGuard(invoice);

  if (payload.lines) {
    invoice.lines = payload.lines.map((line, index) => ({
      label: line.label,
      quantity: line.quantity,
      unit_price_cents: line.unit_price_cents,
      // Calculé, jamais repris de la requête — même règle que le backend.
      amount_cents: Math.round(line.quantity * line.unit_price_cents),
      position: line.position ?? index,
    }));
  }
  if (payload.vat_rate !== null && payload.vat_rate !== undefined) {
    invoice.vat_rate = payload.vat_rate;
  }
  return structuredClone(recompute(invoice));
}

export async function issueInvoice(id: number): Promise<InvoiceOut> {
  await delay(320);
  const invoice = invoices.find((entry) => entry.id === id);
  if (!invoice) notFound("Facture");
  if (invoice.status === "issued") return structuredClone(invoice);
  if (invoice.lines.length === 0) {
    throw new ApiError(409, {
      code: "empty_invoice",
      message: "Une facture sans ligne ne peut pas être émise.",
    });
  }
  invoice.status = "issued";
  invoice.issued_at = new Date().toISOString();
  invoice.number = `${new Date().getFullYear()}-${String(invoices.length + 10).padStart(4, "0")}`;
  return structuredClone(invoice);
}

// ── Devis ─────────────────────────────────────────────────────────────────────────────

export async function listQuotes(
  params: { cursor?: string | null; limit?: number } = {},
): Promise<Page<QuoteOut>> {
  await delay(200);
  return paginate([...quotes].sort((a, b) => b.id - a.id), params.cursor, params.limit ?? 50);
}

export async function createQuote(payload: QuoteCreateRequest): Promise<QuoteOut> {
  await delay(280);
  const created: QuoteOut = {
    id: nextId(),
    client_id: payload.client_id,
    circuit_id: payload.circuit_id,
    title: payload.title,
    starts_at: payload.starts_at,
    ends_at: payload.ends_at,
    amount_cents: payload.amount_cents,
    status: "draft",
    accepted_at: null,
    created_shooting_id: null,
  };
  quotes.push(created);
  return structuredClone(created);
}

export async function acceptQuote(id: number): Promise<QuoteAcceptResponse> {
  await delay(320);
  const quote = quotes.find((entry) => entry.id === id);
  if (!quote) notFound("Devis");
  if (quote.status !== "accepted") {
    quote.status = "accepted";
    quote.accepted_at = new Date().toISOString();
    quote.created_shooting_id = nextId();
  }
  return {
    quote: structuredClone(quote),
    created_shooting: { id: quote.created_shooting_id as number, title: quote.title },
  };
}

// ── Tableau de bord ───────────────────────────────────────────────────────────────────

export async function dashboard(
  _params: { from?: string | null; to?: string | null } = {},
): Promise<DashboardOut> {
  await delay(240);
  const revenue = invoices
    .filter((invoice) => invoice.status === "issued")
    .reduce((sum, invoice) => sum + invoice.total_cents, 0);
  return {
    revenue_cents: revenue,
    shootings_done: 6,
    shootings_upcoming: quotes.filter((quote) => quote.status === "accepted").length + 1,
    media_ingested: { real: 300, simulated: 8117, total: 8417 },
    auto_attach_rate: 0.569,
  };
}
