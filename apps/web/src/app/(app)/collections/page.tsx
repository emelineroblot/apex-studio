"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import * as collectionsApi from "@/lib/api/resources/collections";
import * as clientsApi from "@/lib/api/resources/clients";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { COLLECTION_STATUS_LABELS } from "@/lib/labels";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Field, inputClassName } from "@/components/ui/Field";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import type { ClientOut, CollectionStatus } from "@/lib/api/types";

const STATUS_TONE: Record<CollectionStatus, BadgeTone> = {
  draft: "neutral",
  published: "ok",
  closed: "warn",
};

export default function CollectionsPage() {
  const { data, loading, error, reload } = useAsync(() => collectionsApi.list(null, 50), []);
  const [creating, setCreating] = useState(false);

  return (
    <div>
      <PageHeader
        title="Collections"
        description="Composées depuis la recherche, publiées pour le client (consultation au jalon suivant)."
        actions={<Button onClick={() => setCreating(true)}>Nouvelle collection</Button>}
      />

      {loading ? <Spinner label="Chargement des collections…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error ? (
        !data || data.items.length === 0 ? (
          <EmptyState
            title="Aucune collection"
            description="Composez-en une depuis la recherche (« ajouter les résultats à une collection »), ou créez-la ici."
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((c) => (
              <li key={c.id}>
                <Link href={`/collections/${c.id}`} className="block focus-visible:outline-2 focus-visible:outline-accent-600">
                  <Card className="h-full transition-shadow hover:shadow-md">
                    <div className="flex items-start justify-between gap-2">
                      <h2 className="text-sm font-semibold text-ink-900">{c.title}</h2>
                      <Badge tone={STATUS_TONE[c.status]}>{COLLECTION_STATUS_LABELS[c.status]}</Badge>
                    </div>
                    {c.description ? <p className="mt-1 text-xs text-ink-500">{c.description}</p> : null}
                    <p className="mt-3 text-xs text-ink-400">
                      {c.items.length} média{c.items.length > 1 ? "s" : ""}
                    </p>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )
      ) : null}

      <CreateCollectionModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false);
          reload();
        }}
      />
    </div>
  );
}

function CreateCollectionModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [clientId, setClientId] = useState<number | "">("");
  const [clients, setClients] = useState<ClientOut[] | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && clients === null) {
      clientsApi.list({ limit: 100 }).then((page) => setClients(page.items));
    }
  }, [open, clients]);

  async function submit() {
    if (!title.trim() || clientId === "") {
      setError("Titre et client sont requis.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await collectionsApi.create({ client_id: clientId, title: title.trim() });
      setTitle("");
      setClientId("");
      onCreated();
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Nouvelle collection">
      <div className="flex flex-col gap-3">
        <Field label="Titre" required>
          {(p) => <input {...p} value={title} onChange={(e) => setTitle(e.target.value)} className={inputClassName()} />}
        </Field>
        <Field label="Client" required>
          {(p) => (
            <select
              {...p}
              value={clientId}
              onChange={(e) => setClientId(e.target.value ? Number(e.target.value) : "")}
              className={inputClassName()}
            >
              <option value="">— Choisir —</option>
              {(clients ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        {error ? <p className="text-sm text-danger-600">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button onClick={submit} loading={submitting}>
            Créer
          </Button>
        </div>
      </div>
    </Modal>
  );
}
