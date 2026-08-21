/**
 * Libellés et formats de la facturation.
 *
 * Les libellés sont dérivés des énumérations du contrat via `satisfies Record<Status, …>` :
 * si une valeur apparaît un jour côté backend sans être traduite ici, c'est le compilateur
 * qui le dit. C'est la classe de régression revenue trois fois en J1 — un ensemble fermé
 * côté modèle et un dictionnaire maintenu à la main de l'autre.
 */
import type { BadgeTone } from "@/components/ui/Badge";
import type { DeliveryReadiness, InvoiceStatus, QuoteStatus } from "@/lib/api/types";

const euros = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

/** Les montants circulent en centimes de bout en bout — jamais de flottant en base, ni
 * dans le contrat, ni ici : la division n'a lieu qu'au moment de l'affichage. */
export function formatEuros(cents: number | null | undefined): string {
  if (cents == null) return "—";
  return euros.format(cents / 100);
}

export const INVOICE_STATUS_LABELS = {
  draft: "Brouillon",
  issued: "Émise",
} satisfies Record<InvoiceStatus, string>;

export const INVOICE_STATUS_TONES = {
  draft: "neutral",
  issued: "ok",
} satisfies Record<InvoiceStatus, BadgeTone>;

export const QUOTE_STATUS_LABELS = {
  draft: "Brouillon",
  sent: "Envoyé",
  accepted: "Accepté",
  refused: "Refusé",
} satisfies Record<QuoteStatus, string>;

export const QUOTE_STATUS_TONES = {
  draft: "neutral",
  sent: "accent",
  accepted: "ok",
  refused: "danger",
} satisfies Record<QuoteStatus, BadgeTone>;

export const DELIVERY_STATUS_LABELS = {
  pending: "En attente",
  building: "En préparation",
  ready: "Prête",
  failed: "Échec",
} satisfies Record<DeliveryReadiness, string>;

export const DELIVERY_STATUS_TONES = {
  pending: "neutral",
  building: "accent",
  ready: "ok",
  failed: "danger",
} satisfies Record<DeliveryReadiness, BadgeTone>;
