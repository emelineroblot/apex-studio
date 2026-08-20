"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAsync } from "@/hooks/useAsync";
import * as circuitsApi from "@/lib/api/resources/circuits";
import type { CircuitCreate } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { Modal } from "@/components/ui/Modal";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

function CircuitForm({ onSubmit, onCancel }: { onSubmit: (p: CircuitCreate) => Promise<void>; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("France");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        city: city.trim() || null,
        country: country.trim() || null,
        timezone: "Europe/Paris",
      });
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <Field label="Nom du circuit" required>
        {(p) => <input {...p} required value={name} onChange={(e) => setName(e.target.value)} className={inputClassName()} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Ville">
          {(p) => <input {...p} value={city} onChange={(e) => setCity(e.target.value)} className={inputClassName()} />}
        </Field>
        <Field label="Pays">
          {(p) => <input {...p} value={country} onChange={(e) => setCountry(e.target.value)} className={inputClassName()} />}
        </Field>
      </div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" loading={submitting}>
          Créer le circuit
        </Button>
      </div>
    </form>
  );
}

export default function CircuitsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "owner";
  const [createOpen, setCreateOpen] = useState(false);
  const { data, loading, error, reload } = useAsync(() => circuitsApi.list({ limit: 100 }), []);

  return (
    <div>
      <PageHeader
        title="Circuits"
        description="Référentiel des lieux de shooting."
        actions={canWrite ? <Button onClick={() => setCreateOpen(true)}>Nouveau circuit</Button> : undefined}
      />

      {loading ? <Spinner label="Chargement des circuits…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data ? (
        data.items.length === 0 ? (
          <EmptyState
            title="Aucun circuit enregistré"
            description="Ajoutez un circuit pour pouvoir y programmer un shooting."
            action={canWrite ? <Button onClick={() => setCreateOpen(true)}>Nouveau circuit</Button> : undefined}
          />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-ink-100 bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">Nom</th>
                  <th scope="col" className="px-4 py-3 font-medium">Ville</th>
                  <th scope="col" className="px-4 py-3 font-medium">Pays</th>
                  <th scope="col" className="px-4 py-3 font-medium">Fuseau horaire</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id} className="border-b border-ink-50 last:border-0 hover:bg-ink-50">
                    <td className="px-4 py-3 font-medium text-ink-900">{c.name}</td>
                    <td className="px-4 py-3 text-ink-600">{c.city ?? "—"}</td>
                    <td className="px-4 py-3 text-ink-600">{c.country ?? "—"}</td>
                    <td className="px-4 py-3 text-ink-600">{c.timezone ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      ) : null}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Nouveau circuit">
        <CircuitForm
          onCancel={() => setCreateOpen(false)}
          onSubmit={async (payload) => {
            await circuitsApi.create(payload);
            setCreateOpen(false);
            reload();
          }}
        />
      </Modal>
    </div>
  );
}
