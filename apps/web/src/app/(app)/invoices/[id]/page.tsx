"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import * as billingApi from "@/lib/api/resources/billing";
import type { InvoiceLineIn, InvoiceOut } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { formatEuros, INVOICE_STATUS_LABELS, INVOICE_STATUS_TONES } from "@/lib/billing";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { inputClassName } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Notice } from "@/components/ui/Notice";
import { ErrorState, Spinner } from "@/components/ui/States";

type DraftLine = InvoiceLineIn & { key: string };

function toDraft(invoice: InvoiceOut): DraftLine[] {
  return invoice.lines.map((line, index) => ({
    key: `${index}`,
    label: line.label,
    quantity: line.quantity,
    unit_price_cents: line.unit_price_cents,
    position: line.position,
  }));
}

/**
 * Détail d'une facture — modifiable tant qu'elle est brouillon, verrouillée dès l'émission.
 *
 * Le verrouillage n'est pas qu'un `disabled` : un bandeau explique *pourquoi* les champs
 * ne répondent plus. Une interface qui grise ses champs sans rien dire laisse penser à une
 * panne. Le backend refuserait de toute façon (`409`), et le trigger PL/pgSQL derrière lui,
 * mais un utilisateur ne devrait jamais avoir à déclencher une erreur pour comprendre une
 * règle.
 */
export default function InvoiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const invoiceId = Number(id);

  const [invoice, setInvoice] = useState<InvoiceOut | null>(null);
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [vatRate, setVatRate] = useState(0.2);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmIssue, setConfirmIssue] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const detail = await billingApi.getInvoice(invoiceId);
      setInvoice(detail);
      setLines(toDraft(detail));
      setVatRate(detail.vat_rate);
      setError(null);
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const locked = invoice?.status === "issued";

  function patchLine(key: string, patch: Partial<InvoiceLineIn>) {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  }

  async function save() {
    setBusy(true);
    try {
      const updated = await billingApi.patchInvoice(invoiceId, {
        lines: lines.map(({ key: _key, ...line }) => line),
        vat_rate: vatRate,
      });
      setInvoice(updated);
      setLines(toDraft(updated));
      setError(null);
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function issue() {
    setBusy(true);
    setConfirmIssue(false);
    try {
      const issued = await billingApi.issueInvoice(invoiceId);
      setInvoice(issued);
      setLines(toDraft(issued));
      setError(null);
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner label="Chargement de la facture…" />;
  if (!invoice) return <ErrorState message={error ?? "Facture introuvable."} onRetry={load} />;

  const subtotal = lines.reduce(
    (sum, line) => sum + Math.round(line.quantity * line.unit_price_cents),
    0,
  );

  return (
    <div>
      <PageHeader
        title={invoice.number ?? `Facture brouillon #${invoice.id}`}
        description={
          locked
            ? `Émise le ${formatDateTime(invoice.issued_at)}`
            : "Brouillon — ajustez les lignes avant d'émettre."
        }
      />

      <div className="mb-4 flex items-center gap-3">
        <Badge tone={INVOICE_STATUS_TONES[invoice.status]}>
          {INVOICE_STATUS_LABELS[invoice.status]}
        </Badge>
        <Link href="/invoices" className="text-sm text-ink-600 underline hover:no-underline">
          Toutes les factures
        </Link>
      </div>

      {locked ? (
        <div className="mb-4">
          <Notice tone="ok">
            <p>
              <strong>Cette facture est émise.</strong> Son numéro, ses lignes et son montant
              sont figés définitivement — c&apos;est ce qui garantit qu&apos;un document déjà
              envoyé à un client ne changera jamais après coup.
            </p>
          </Notice>
        </div>
      ) : null}

      {error ? (
        <div className="mb-4">
          <Notice tone="danger" onDismiss={() => setError(null)}>
            {error}
          </Notice>
        </div>
      ) : null}

      <Card className="p-0">
        <table className="min-w-full text-sm">
          <thead className="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="px-4 py-3 font-semibold">Prestation</th>
              <th className="px-4 py-3 font-semibold">Quantité</th>
              <th className="px-4 py-3 font-semibold">Prix unitaire</th>
              <th className="px-4 py-3 text-right font-semibold">Montant</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {lines.map((line) => (
              <tr key={line.key}>
                <td className="px-4 py-2">
                  <input
                    value={line.label}
                    disabled={locked}
                    onChange={(event) => patchLine(line.key, { label: event.target.value })}
                    className={inputClassName()}
                    aria-label="Libellé de la prestation"
                  />
                </td>
                <td className="px-4 py-2">
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={line.quantity}
                    disabled={locked}
                    onChange={(event) =>
                      patchLine(line.key, { quantity: Number(event.target.value) })
                    }
                    className={inputClassName("w-24")}
                    aria-label="Quantité"
                  />
                </td>
                <td className="px-4 py-2">
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={line.unit_price_cents}
                    disabled={locked}
                    onChange={(event) =>
                      patchLine(line.key, { unit_price_cents: Number(event.target.value) })
                    }
                    className={inputClassName("w-32")}
                    aria-label="Prix unitaire en centimes"
                  />
                </td>
                <td className="px-4 py-2 text-right font-medium text-ink-900">
                  {/* Recalculé à l'affichage comme il l'est côté serveur : le montant n'est
                      jamais une valeur saisie. */}
                  {formatEuros(Math.round(line.quantity * line.unit_price_cents))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <label className="flex items-center gap-2 text-sm text-ink-700">
          TVA
          <input
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={vatRate}
            disabled={locked}
            onChange={(event) => setVatRate(Number(event.target.value))}
            className={inputClassName("w-24")}
          />
        </label>
        <div className="text-right">
          <p className="text-sm text-ink-600">
            Sous-total {formatEuros(locked ? invoice.subtotal_cents : subtotal)}
          </p>
          <p className="text-2xl font-semibold text-ink-900">
            {formatEuros(locked ? invoice.total_cents : Math.round(subtotal * (1 + vatRate)))}
          </p>
        </div>
      </div>

      {!locked ? (
        <div className="mt-6 flex gap-3">
          <Button variant="secondary" onClick={() => void save()} loading={busy}>
            Enregistrer le brouillon
          </Button>
          <Button onClick={() => setConfirmIssue(true)} disabled={busy || lines.length === 0}>
            Émettre la facture
          </Button>
        </div>
      ) : null}

      <Modal
        open={confirmIssue}
        title="Émettre cette facture ?"
        onClose={() => setConfirmIssue(false)}
      >
        <p className="text-sm text-ink-700">
          L&apos;émission attribue un numéro définitif et fige le document. Après cela, plus
          aucune modification ne sera possible — ni depuis cet écran, ni ailleurs.
        </p>
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmIssue(false)}>
            Annuler
          </Button>
          <Button onClick={() => void issue()} loading={busy}>
            Émettre définitivement
          </Button>
        </div>
      </Modal>
    </div>
  );
}
