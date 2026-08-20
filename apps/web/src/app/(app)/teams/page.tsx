"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAsync } from "@/hooks/useAsync";
import * as teamsApi from "@/lib/api/resources/teams";
import * as clientsApi from "@/lib/api/resources/clients";
import type { ClientOut, TeamCreate } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { Modal } from "@/components/ui/Modal";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

function TeamForm({
  clients,
  onSubmit,
  onCancel,
}: {
  clients: ClientOut[];
  onSubmit: (p: TeamCreate) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [clientId, setClientId] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), client_id: clientId ? Number(clientId) : null });
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <Field label="Nom de l'écurie" required>
        {(p) => <input {...p} required value={name} onChange={(e) => setName(e.target.value)} className={inputClassName()} />}
      </Field>
      <Field label="Client associé" hint="Facultatif — laisse « Aucun » si l'écurie n'est pas encore cliente.">
        {(p) => (
          <select {...p} value={clientId} onChange={(e) => setClientId(e.target.value)} className={inputClassName()}>
            <option value="">Aucun</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" loading={submitting}>
          Créer l&apos;écurie
        </Button>
      </div>
    </form>
  );
}

export default function TeamsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "owner";
  const [createOpen, setCreateOpen] = useState(false);
  const { data, loading, error, reload } = useAsync(() => teamsApi.list({ limit: 100 }), []);
  const { data: clientsPage } = useAsync(() => clientsApi.list({ limit: 100 }), []);
  const clientsById = new Map((clientsPage?.items ?? []).map((c) => [c.id, c]));

  return (
    <div>
      <PageHeader
        title="Écuries"
        description="Référentiel des équipes engagées sur les shootings."
        actions={canWrite ? <Button onClick={() => setCreateOpen(true)}>Nouvelle écurie</Button> : undefined}
      />

      {loading ? <Spinner label="Chargement des écuries…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data ? (
        data.items.length === 0 ? (
          <EmptyState
            title="Aucune écurie enregistrée"
            action={canWrite ? <Button onClick={() => setCreateOpen(true)}>Nouvelle écurie</Button> : undefined}
          />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-ink-100 bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">Nom</th>
                  <th scope="col" className="px-4 py-3 font-medium">Client associé</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.id} className="border-b border-ink-50 last:border-0 hover:bg-ink-50">
                    <td className="px-4 py-3 font-medium text-ink-900">{t.name}</td>
                    <td className="px-4 py-3 text-ink-600">
                      {t.client_id ? (clientsById.get(t.client_id)?.name ?? `#${t.client_id}`) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      ) : null}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Nouvelle écurie">
        <TeamForm
          clients={clientsPage?.items ?? []}
          onCancel={() => setCreateOpen(false)}
          onSubmit={async (payload) => {
            await teamsApi.create(payload);
            setCreateOpen(false);
            reload();
          }}
        />
      </Modal>
    </div>
  );
}
