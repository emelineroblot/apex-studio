"use client";

import { useState } from "react";
import type { ClientCreate, ClientOut } from "@/lib/api/types";
import { CLIENT_KIND_LABELS } from "@/lib/labels";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { Field, inputClassName } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

const KIND_OPTIONS = Object.entries(CLIENT_KIND_LABELS);

export function ClientForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: ClientOut;
  onSubmit: (payload: ClientCreate) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [kind, setKind] = useState<string>(initial?.kind ?? "team");
  const [contactName, setContactName] = useState(initial?.contact_name ?? "");
  const [contactEmail, setContactEmail] = useState(initial?.contact_email ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [address, setAddress] = useState(initial?.address ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        kind: kind as ClientCreate["kind"],
        contact_name: contactName.trim() || null,
        contact_email: contactEmail.trim() || null,
        phone: phone.trim() || null,
        address: address.trim() || null,
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
      <Field label="Nom" required>
        {(p) => (
          <input {...p} required value={name} onChange={(e) => setName(e.target.value)} className={inputClassName()} />
        )}
      </Field>
      <Field label="Type de client" required>
        {(p) => (
          <select {...p} required value={kind} onChange={(e) => setKind(e.target.value)} className={inputClassName()}>
            {KIND_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nom du contact">
          {(p) => <input {...p} value={contactName ?? ""} onChange={(e) => setContactName(e.target.value)} className={inputClassName()} />}
        </Field>
        <Field label="E-mail du contact">
          {(p) => (
            <input
              {...p}
              type="email"
              value={contactEmail ?? ""}
              onChange={(e) => setContactEmail(e.target.value)}
              className={inputClassName()}
            />
          )}
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Téléphone">
          {(p) => <input {...p} value={phone ?? ""} onChange={(e) => setPhone(e.target.value)} className={inputClassName()} />}
        </Field>
        <Field label="Adresse">
          {(p) => <input {...p} value={address ?? ""} onChange={(e) => setAddress(e.target.value)} className={inputClassName()} />}
        </Field>
      </div>
      <Field label="Notes">
        {(p) => (
          <textarea {...p} value={notes ?? ""} onChange={(e) => setNotes(e.target.value)} rows={3} className={inputClassName()} />
        )}
      </Field>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" loading={submitting}>
          {initial ? "Enregistrer" : "Créer le client"}
        </Button>
      </div>
    </form>
  );
}
