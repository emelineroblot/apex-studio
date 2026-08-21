"use client";

import { useState } from "react";
import Link from "next/link";
import * as billingApi from "@/lib/api/resources/billing";
import type { InvoiceOut, InvoiceStatus } from "@/lib/api/types";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { formatEuros, INVOICE_STATUS_LABELS, INVOICE_STATUS_TONES } from "@/lib/billing";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";

const FILTERS: { value: InvoiceStatus | "all"; label: string }[] = [
  { value: "all", label: "Toutes" },
  { value: "draft", label: "Brouillons" },
  { value: "issued", label: "Émises" },
];

export default function InvoicesPage() {
  const [status, setStatus] = useState<InvoiceStatus | "all">("all");
  const { data, loading, error, reload } = useAsync(
    () => billingApi.listInvoices({ status: status === "all" ? null : status }),
    [status],
  );

  return (
    <div>
      <PageHeader
        title="Factures"
        description="Une facture émise est définitive : ni ses lignes ni son montant ne peuvent changer."
      />

      <div className="mb-4 flex gap-2">
        {FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            onClick={() => setStatus(filter.value)}
            aria-pressed={status === filter.value}
            className={
              status === filter.value
                ? "rounded-lg bg-accent-600 px-3 py-1.5 text-sm font-medium text-white"
                : "rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-50"
            }
          >
            {filter.label}
          </button>
        ))}
      </div>

      {loading ? <Spinner label="Chargement des factures…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data && data.items.length === 0 ? (
        <EmptyState
          title="Aucune facture"
          description="Les factures sont créées à partir d'une sélection client validée."
        />
      ) : null}

      {!loading && !error && data && data.items.length > 0 ? (
        <Card className="p-0">
          <table className="min-w-full text-sm">
            <thead className="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Numéro</th>
                <th className="px-4 py-3 font-semibold">État</th>
                <th className="px-4 py-3 font-semibold">Émise le</th>
                <th className="px-4 py-3 text-right font-semibold">Total TTC</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {data.items.map((invoice: InvoiceOut) => (
                <tr key={invoice.id} className="hover:bg-ink-50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/invoices/${invoice.id}`}
                      className="font-medium text-accent-700 underline hover:no-underline"
                    >
                      {invoice.number ?? `Brouillon #${invoice.id}`}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={INVOICE_STATUS_TONES[invoice.status]}>
                      {INVOICE_STATUS_LABELS[invoice.status]}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-ink-700">{formatDate(invoice.issued_at)}</td>
                  <td className="px-4 py-3 text-right font-medium text-ink-900">
                    {formatEuros(invoice.total_cents)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : null}
    </div>
  );
}
