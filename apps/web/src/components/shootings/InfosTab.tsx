"use client";

import { useState } from "react";
import type { CircuitOut, ClientOut, ShootingOut } from "@/lib/api/types";
import * as shootingsApi from "@/lib/api/resources/shootings";
import { SHOOTING_STATUS_LABELS } from "@/lib/labels";
import { formatBytes, formatDateTime, toDateTimeLocalInput } from "@/lib/format";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export function InfosTab({
  shooting,
  clients,
  circuits,
  canWrite,
  onUpdated,
}: {
  shooting: ShootingOut;
  clients: ClientOut[];
  circuits: CircuitOut[];
  canWrite: boolean;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);

  if (!editing) {
    const circuit = circuits.find((c) => c.id === shooting.circuit_id);
    const client = clients.find((c) => c.id === shooting.client_id);
    return (
      <Card>
        <div className="flex items-start justify-between gap-3">
          <dl className="grid flex-1 gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">Statut</dt>
              <dd className="mt-0.5 text-sm text-ink-800">{SHOOTING_STATUS_LABELS[shooting.status]}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">Circuit</dt>
              <dd className="mt-0.5 text-sm text-ink-800">{circuit?.name ?? `#${shooting.circuit_id}`}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">Client</dt>
              <dd className="mt-0.5 text-sm text-ink-800">{client?.name ?? "Sans client"}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">Quota de stockage</dt>
              <dd className="mt-0.5 text-sm text-ink-800">{formatBytes(shooting.quota_bytes)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">Début</dt>
              <dd className="mt-0.5 text-sm text-ink-800">{formatDateTime(shooting.starts_at)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">Fin</dt>
              <dd className="mt-0.5 text-sm text-ink-800">{formatDateTime(shooting.ends_at)}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium uppercase tracking-wide text-ink-400">Notes</dt>
              <dd className="mt-0.5 whitespace-pre-wrap text-sm text-ink-800">{shooting.notes ?? "—"}</dd>
            </div>
          </dl>
          {canWrite ? (
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
              Modifier
            </Button>
          ) : null}
        </div>
      </Card>
    );
  }

  return (
    <EditForm
      shooting={shooting}
      clients={clients}
      circuits={circuits}
      onCancel={() => setEditing(false)}
      onSaved={() => {
        setEditing(false);
        onUpdated();
      }}
    />
  );
}

function EditForm({
  shooting,
  clients,
  circuits,
  onCancel,
  onSaved,
}: {
  shooting: ShootingOut;
  clients: ClientOut[];
  circuits: CircuitOut[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(shooting.title);
  const [status, setStatus] = useState(shooting.status);
  const [clientId, setClientId] = useState(shooting.client_id ? String(shooting.client_id) : "");
  const [circuitId, setCircuitId] = useState(String(shooting.circuit_id));
  const [startsAt, setStartsAt] = useState(toDateTimeLocalInput(shooting.starts_at));
  const [endsAt, setEndsAt] = useState(toDateTimeLocalInput(shooting.ends_at));
  const [notes, setNotes] = useState(shooting.notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await shootingsApi.update(shooting.id, {
        title: title.trim(),
        status,
        client_id: clientId ? Number(clientId) : null,
        circuit_id: Number(circuitId),
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
        notes: notes.trim() || null,
      });
      onSaved();
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        <Field label="Titre" required>
          {(p) => <input {...p} required value={title} onChange={(e) => setTitle(e.target.value)} className={inputClassName()} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Statut">
            {(p) => (
              <select {...p} value={status} onChange={(e) => setStatus(e.target.value as typeof status)} className={inputClassName()}>
                <option value="planned">Programmé</option>
                <option value="done">Réalisé</option>
              </select>
            )}
          </Field>
          <Field label="Circuit" required>
            {(p) => (
              <select {...p} required value={circuitId} onChange={(e) => setCircuitId(e.target.value)} className={inputClassName()}>
                {circuits.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>
        <Field label="Client">
          {(p) => (
            <select {...p} value={clientId} onChange={(e) => setClientId(e.target.value)} className={inputClassName()}>
              <option value="">Sans client</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Début" required>
            {(p) => (
              <input {...p} type="datetime-local" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} className={inputClassName()} />
            )}
          </Field>
          <Field label="Fin" required>
            {(p) => (
              <input {...p} type="datetime-local" required value={endsAt} onChange={(e) => setEndsAt(e.target.value)} className={inputClassName()} />
            )}
          </Field>
        </div>
        <Field label="Notes">
          {(p) => <textarea {...p} value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className={inputClassName()} />}
        </Field>

        {error ? <Notice tone="danger">{error}</Notice> : null}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Annuler
          </Button>
          <Button type="submit" loading={submitting}>
            Enregistrer
          </Button>
        </div>
      </form>
    </Card>
  );
}
