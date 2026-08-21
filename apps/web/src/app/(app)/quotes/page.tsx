"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import * as billingApi from "@/lib/api/resources/billing";
import * as clientsApi from "@/lib/api/resources/clients";
import * as circuitsApi from "@/lib/api/resources/circuits";
import type { CircuitOut, ClientOut, QuoteOut } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { formatEuros, QUOTE_STATUS_LABELS, QUOTE_STATUS_TONES } from "@/lib/billing";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";

/**
 * Devis — établir, puis accepter.
 *
 * L'acceptation **crée le shooting** et redirige dessus : c'est le geste métier complet,
 * pas une simple bascule de statut. La période du devis devient la fenêtre temporelle qui
 * rattachera les photos du week-end, ce que l'écran dit explicitement avant le clic.
 */
export default function QuotesPage() {
  const router = useRouter();
  const [quotes, setQuotes] = useState<QuoteOut[] | null>(null);
  const [clients, setClients] = useState<ClientOut[]>([]);
  const [circuits, setCircuits] = useState<CircuitOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    client_id: "",
    circuit_id: "",
    title: "",
    starts_at: "",
    ends_at: "",
    amount_euros: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [quotePage, clientPage, circuitPage] = await Promise.all([
        billingApi.listQuotes(),
        clientsApi.list(),
        circuitsApi.list(),
      ]);
      setQuotes(quotePage.items);
      setClients(clientPage.items);
      setCircuits(circuitPage.items);
      setError(null);
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await billingApi.createQuote({
        client_id: Number(form.client_id),
        circuit_id: Number(form.circuit_id),
        title: form.title,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        // Saisi en euros, transmis en centimes : les montants ne circulent jamais en
        // flottant au-delà de ce champ.
        amount_cents: Math.round(Number(form.amount_euros) * 100),
      });
      setForm({ client_id: "", circuit_id: "", title: "", starts_at: "", ends_at: "", amount_euros: "" });
      await load();
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function accept(quote: QuoteOut) {
    setBusy(true);
    try {
      const response = await billingApi.acceptQuote(quote.id);
      router.push(`/shootings/${response.created_shooting.id}`);
    } catch (err) {
      setError(friendlyErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Devis"
        description="Accepter un devis crée le shooting correspondant, avec la même période."
      />

      {error ? (
        <div className="mb-4">
          <Notice tone="danger" onDismiss={() => setError(null)}>
            {error}
          </Notice>
        </div>
      ) : null}

      <Card className="mb-6">
        <form onSubmit={create} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Client" required>
            {(inputProps) => (
              <select
                {...inputProps}
                required
                value={form.client_id}
                onChange={(event) => setForm({ ...form, client_id: event.target.value })}
                className={inputClassName()}
              >
                <option value="">—</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Circuit" required>
            {(inputProps) => (
              <select
                {...inputProps}
                required
                value={form.circuit_id}
                onChange={(event) => setForm({ ...form, circuit_id: event.target.value })}
                className={inputClassName()}
              >
                <option value="">—</option>
                {circuits.map((circuit) => (
                  <option key={circuit.id} value={circuit.id}>
                    {circuit.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Intitulé" required>
            {(inputProps) => (
              <input
                {...inputProps}
                required
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
                className={inputClassName()}
                placeholder="Week-end GT — Magny-Cours"
              />
            )}
          </Field>
          <Field label="Début" required hint="Cette période deviendra celle du shooting.">
            {(inputProps) => (
              <input
                {...inputProps}
                required
                type="datetime-local"
                value={form.starts_at}
                onChange={(event) => setForm({ ...form, starts_at: event.target.value })}
                className={inputClassName()}
              />
            )}
          </Field>
          <Field label="Fin" required>
            {(inputProps) => (
              <input
                {...inputProps}
                required
                type="datetime-local"
                value={form.ends_at}
                onChange={(event) => setForm({ ...form, ends_at: event.target.value })}
                className={inputClassName()}
              />
            )}
          </Field>
          <Field label="Montant (€)" required>
            {(inputProps) => (
              <input
                {...inputProps}
                required
                type="number"
                min={0}
                step="0.01"
                value={form.amount_euros}
                onChange={(event) => setForm({ ...form, amount_euros: event.target.value })}
                className={inputClassName()}
              />
            )}
          </Field>
          <div className="sm:col-span-2 lg:col-span-3">
            <Button type="submit" loading={busy}>
              Créer le devis
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Spinner label="Chargement des devis…" /> : null}
      {!loading && error && !quotes ? <ErrorState message={error} onRetry={load} /> : null}
      {!loading && quotes && quotes.length === 0 ? (
        <EmptyState title="Aucun devis" description="Établissez un devis pour un événement à venir." />
      ) : null}

      {!loading && quotes && quotes.length > 0 ? (
        <Card className="p-0">
          <table className="min-w-full text-sm">
            <thead className="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Intitulé</th>
                <th className="px-4 py-3 font-semibold">Période</th>
                <th className="px-4 py-3 font-semibold">État</th>
                <th className="px-4 py-3 text-right font-semibold">Montant</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {quotes.map((quote) => (
                <tr key={quote.id}>
                  <td className="px-4 py-3 font-medium text-ink-900">{quote.title}</td>
                  <td className="px-4 py-3 text-ink-700">
                    {formatDateTime(quote.starts_at)} → {formatDateTime(quote.ends_at)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={QUOTE_STATUS_TONES[quote.status]}>
                      {QUOTE_STATUS_LABELS[quote.status]}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right text-ink-900">
                    {formatEuros(quote.amount_cents)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {quote.status === "accepted" && quote.created_shooting_id ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => router.push(`/shootings/${quote.created_shooting_id}`)}
                      >
                        Voir le shooting
                      </Button>
                    ) : quote.status === "refused" ? null : (
                      <Button size="sm" disabled={busy} onClick={() => void accept(quote)}>
                        Accepter
                      </Button>
                    )}
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
