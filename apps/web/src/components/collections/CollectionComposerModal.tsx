"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import * as collectionsApi from "@/lib/api/resources/collections";
import * as clientsApi from "@/lib/api/resources/clients";
import type { AddItemsPayload } from "@/lib/api/resources/collections";
import type { ClientOut, CollectionOut } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Spinner } from "@/components/ui/States";

export type CompositionSource =
  | { type: "selection"; mediaIds: number[] }
  | { type: "search"; filters: AddItemsPayload["from_search"]; resultCount: number };

/**
 * Composer une collection depuis une sélection de résultats de recherche (§ tâche 4 du
 * brief) — soit la sélection explicite courante (`Shift`+clic sur `/search`), soit
 * **tous** les résultats de la recherche active (`from_search`, non paginé côté serveur).
 */
export function CollectionComposerModal({
  open,
  onClose,
  source,
}: {
  open: boolean;
  onClose: () => void;
  source: CompositionSource | null;
}) {
  const [collections, setCollections] = useState<CollectionOut[] | null>(null);
  const [clients, setClients] = useState<ClientOut[] | null>(null);
  const [targetId, setTargetId] = useState<number | "new">("new");
  const [newTitle, setNewTitle] = useState("");
  const [newClientId, setNewClientId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<{ collectionId: number; added: number; skipped: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setError(null);
    Promise.all([collectionsApi.list(null, 50), clientsApi.list({ limit: 100 })])
      .then(([collectionsPage, clientsPage]) => {
        setCollections(collectionsPage.items.filter((c) => c.status !== "closed"));
        setClients(clientsPage.items);
      })
      .catch((err) => setError(err));
  }, [open]);

  const count = source?.type === "selection" ? source.mediaIds.length : (source?.resultCount ?? 0);

  async function handleSubmit() {
    if (!source) return;
    setBusy(true);
    setError(null);
    try {
      let collectionId: number;
      if (targetId === "new") {
        if (!newTitle.trim() || newClientId === "") {
          throw new Error("Titre et client sont requis pour créer une nouvelle collection.");
        }
        const created = await collectionsApi.create({ client_id: newClientId, title: newTitle.trim() });
        collectionId = created.id;
      } else {
        collectionId = targetId;
      }
      const payload: AddItemsPayload =
        source.type === "selection" ? { media_ids: source.mediaIds } : { from_search: source.filters };
      const response = await collectionsApi.addItems(collectionId, payload);
      setResult({ collectionId, added: response.added, skipped: response.skipped_duplicates });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Ajouter à une collection">
      {result ? (
        <div className="flex flex-col gap-3">
          <Notice tone="ok">
            {result.added} média{result.added > 1 ? "s" : ""} ajouté{result.added > 1 ? "s" : ""}
            {result.skipped > 0 ? ` (${result.skipped} déjà présent${result.skipped > 1 ? "s" : ""}, ignoré${result.skipped > 1 ? "s" : ""})` : ""}.
          </Notice>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Fermer
            </Button>
            <Link href={`/collections/${result.collectionId}`}>
              <Button onClick={onClose}>Ouvrir la collection</Button>
            </Link>
          </div>
        </div>
      ) : !collections || !clients ? (
        <Spinner label="Chargement des collections…" />
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-ink-600">
            {source?.type === "search"
              ? `Les ${count} résultats de la recherche actuelle seront ajoutés (pas seulement la page affichée).`
              : `${count} média${count > 1 ? "s" : ""} sélectionné${count > 1 ? "s" : ""}.`}
          </p>

          {error ? <Notice tone="danger">{friendlyErrorMessage(error)}</Notice> : null}

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-ink-800">Collection cible</legend>
            {collections.map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-sm text-ink-700">
                <input
                  type="radio"
                  name="collection-target"
                  checked={targetId === c.id}
                  onChange={() => setTargetId(c.id)}
                  className="h-4 w-4 text-accent-600"
                />
                {c.title} <span className="text-ink-400">({c.items.length} médias)</span>
              </label>
            ))}
            <label className="flex items-center gap-2 text-sm text-ink-700">
              <input
                type="radio"
                name="collection-target"
                checked={targetId === "new"}
                onChange={() => setTargetId("new")}
                className="h-4 w-4 text-accent-600"
              />
              Nouvelle collection
            </label>
          </fieldset>

          {targetId === "new" ? (
            <div className="flex flex-col gap-3 rounded-lg border border-ink-100 bg-ink-50 p-3">
              <Field label="Titre" required>
                {(inputProps) => (
                  <input
                    {...inputProps}
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    className={inputClassName()}
                  />
                )}
              </Field>
              <Field label="Client" required>
                {(inputProps) => (
                  <select
                    {...inputProps}
                    value={newClientId}
                    onChange={(e) => setNewClientId(e.target.value ? Number(e.target.value) : "")}
                    className={inputClassName()}
                  >
                    <option value="">— Choisir —</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </div>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              Annuler
            </Button>
            <Button onClick={handleSubmit} loading={busy}>
              Ajouter
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
