"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAsync } from "@/hooks/useAsync";
import * as driversApi from "@/lib/api/resources/drivers";
import type { DriverCreate } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { Modal } from "@/components/ui/Modal";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

function DriverForm({ onSubmit, onCancel }: { onSubmit: (p: DriverCreate) => Promise<void>; onCancel: () => void }) {
  const [fullName, setFullName] = useState("");
  const [nationality, setNationality] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ full_name: fullName.trim(), nationality: nationality.trim() || null });
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <Field label="Nom complet" required>
        {(p) => <input {...p} required value={fullName} onChange={(e) => setFullName(e.target.value)} className={inputClassName()} />}
      </Field>
      <Field label="Nationalité" hint="Code à deux lettres, ex. FR, IT.">
        {(p) => (
          <input
            {...p}
            value={nationality}
            maxLength={2}
            onChange={(e) => setNationality(e.target.value.toUpperCase())}
            className={inputClassName("uppercase")}
          />
        )}
      </Field>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" loading={submitting}>
          Créer le pilote
        </Button>
      </div>
    </form>
  );
}

export default function DriversPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "owner";
  const [createOpen, setCreateOpen] = useState(false);
  const { data, loading, error, reload } = useAsync(() => driversApi.list({ limit: 100 }), []);

  return (
    <div>
      <PageHeader
        title="Pilotes"
        description="Référentiel des pilotes pouvant être engagés sur un shooting."
        actions={canWrite ? <Button onClick={() => setCreateOpen(true)}>Nouveau pilote</Button> : undefined}
      />

      {loading ? <Spinner label="Chargement des pilotes…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data ? (
        data.items.length === 0 ? (
          <EmptyState
            title="Aucun pilote enregistré"
            action={canWrite ? <Button onClick={() => setCreateOpen(true)}>Nouveau pilote</Button> : undefined}
          />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-ink-100 bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">Nom</th>
                  <th scope="col" className="px-4 py-3 font-medium">Nationalité</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((d) => (
                  <tr key={d.id} className="border-b border-ink-50 last:border-0 hover:bg-ink-50">
                    <td className="px-4 py-3 font-medium text-ink-900">{d.full_name}</td>
                    <td className="px-4 py-3 text-ink-600">{d.nationality ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      ) : null}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Nouveau pilote">
        <DriverForm
          onCancel={() => setCreateOpen(false)}
          onSubmit={async (payload) => {
            await driversApi.create(payload);
            setCreateOpen(false);
            reload();
          }}
        />
      </Modal>
    </div>
  );
}
