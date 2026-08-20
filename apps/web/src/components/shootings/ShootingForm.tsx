"use client";

import { useState } from "react";
import type { CircuitOut, ClientOut, ShootingCreate } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { Field, inputClassName } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

export function ShootingForm({
  clients,
  circuits,
  onSubmit,
  onCancel,
}: {
  clients: ClientOut[];
  circuits: CircuitOut[];
  onSubmit: (payload: ShootingCreate) => Promise<void>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState("");
  const [clientId, setClientId] = useState("");
  const [circuitId, setCircuitId] = useState(circuits[0] ? String(circuits[0].id) : "");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldError(null);

    if (!circuitId) {
      setFieldError("Choisissez un circuit.");
      return;
    }
    if (!startsAt || !endsAt) {
      setFieldError("Renseignez la plage horaire complète.");
      return;
    }
    const start = new Date(startsAt);
    const end = new Date(endsAt);
    if (end <= start) {
      setFieldError("La fin doit être après le début.");
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({
        title: title.trim(),
        client_id: clientId ? Number(clientId) : null,
        circuit_id: Number(circuitId),
        starts_at: start.toISOString(),
        ends_at: end.toISOString(),
        notes: notes.trim() || null,
      });
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <Field label="Titre" required>
        {(p) => <input {...p} required value={title} onChange={(e) => setTitle(e.target.value)} className={inputClassName()} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Circuit" required>
          {(p) => (
            <select {...p} required value={circuitId} onChange={(e) => setCircuitId(e.target.value)} className={inputClassName()}>
              <option value="" disabled>
                Choisir un circuit
              </option>
              {circuits.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Client" hint="Facultatif — peut être ajouté plus tard.">
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
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Début" required>
          {(p) => (
            <input
              {...p}
              type="datetime-local"
              required
              value={startsAt}
              onChange={(e) => setStartsAt(e.target.value)}
              className={inputClassName()}
            />
          )}
        </Field>
        <Field label="Fin" required>
          {(p) => (
            <input
              {...p}
              type="datetime-local"
              required
              value={endsAt}
              onChange={(e) => setEndsAt(e.target.value)}
              className={inputClassName()}
            />
          )}
        </Field>
      </div>
      <Field label="Notes">
        {(p) => <textarea {...p} value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className={inputClassName()} />}
      </Field>

      {fieldError ? <Notice tone="warn">{fieldError}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" loading={submitting}>
          Créer le shooting
        </Button>
      </div>
    </form>
  );
}
