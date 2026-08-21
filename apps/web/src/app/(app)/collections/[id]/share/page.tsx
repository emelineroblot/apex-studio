"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import * as billingApi from "@/lib/api/resources/billing";
import * as collectionsApi from "@/lib/api/resources/collections";
import type { CollectionOut, ShareLinkCreateResponse, ShareLinkOut } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";

const DURATIONS = [7, 14, 30, 90];

function linkState(link: ShareLinkOut): { label: string; tone: "ok" | "neutral" | "danger" } {
  if (link.revoked_at) return { label: "Révoqué", tone: "danger" };
  if (new Date(link.expires_at) <= new Date()) return { label: "Expiré", tone: "neutral" };
  return { label: "Actif", tone: "ok" };
}

/**
 * Partage d'une collection.
 *
 * L'écran est construit autour d'une contrainte : **le lien n'est affiché qu'une fois**.
 * Le backend ne stocke que l'empreinte du jeton, personne ne peut le réafficher — pas même
 * le studio. L'encart de copie est donc volontairement insistant, et la liste en dessous
 * ne montre que des silhouettes de liens, jamais un lien réel.
 */
export default function CollectionSharePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const collectionId = Number(id);

  const [collection, setCollection] = useState<CollectionOut | null>(null);
  const [links, setLinks] = useState<ShareLinkOut[] | null>(null);
  const [created, setCreated] = useState<ShareLinkCreateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [days, setDays] = useState(14);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [detail, list] = await Promise.all([
        collectionsApi.get(collectionId),
        billingApi.listShareLinks(collectionId),
      ]);
      setCollection(detail);
      setLinks(list);
      setError(null);
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [collectionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createLink() {
    setBusy(true);
    try {
      const response = await billingApi.createShareLink(collectionId, days);
      setCreated(response);
      setCopied(false);
      setLinks(await billingApi.listShareLinks(collectionId));
      setError(null);
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(linkId: string) {
    setBusy(true);
    try {
      await billingApi.revokeShareLink(linkId);
      setLinks(await billingApi.listShareLinks(collectionId));
      setError(null);
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.url);
      setCopied(true);
    } catch {
      // Presse-papiers refusé (contexte non sécurisé, permission) : le lien reste
      // sélectionnable à la main dans le champ ci-dessus — on ne perd rien.
      setCopied(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Partager la collection"
        description={collection ? collection.title : "Chargement…"}
      />

      {error ? (
        <div className="mb-4">
          <Notice tone="danger" onDismiss={() => setError(null)}>
            {error}
          </Notice>
        </div>
      ) : null}

      {created ? (
        <Card className="mb-6 border-accent-200 bg-accent-50">
          <p className="text-sm font-semibold text-accent-800">
            Copiez ce lien maintenant — il ne sera plus affiché.
          </p>
          <p className="mt-1 text-xs text-accent-700">
            Seule son empreinte est conservée : personne, pas même vous, ne pourra le
            retrouver ensuite. En cas de perte, créez-en un nouveau et révoquez celui-ci.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              readOnly
              value={created.url}
              onFocus={(event) => event.currentTarget.select()}
              className={inputClassName("max-w-xl font-mono text-xs")}
              aria-label="Lien de partage à copier"
            />
            <Button onClick={() => void copy()} variant="secondary">
              {copied ? "Copié" : "Copier"}
            </Button>
            <Button onClick={() => setCreated(null)} variant="ghost">
              J&apos;ai copié le lien
            </Button>
          </div>
          <p className="mt-2 text-xs text-accent-700">
            Expire le {formatDateTime(created.expires_at)}.
          </p>
        </Card>
      ) : null}

      <Card className="mb-6">
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-48">
            <Field label="Durée de validité">
              {(inputProps) => (
                <select
                  {...inputProps}
                  value={days}
                  onChange={(event) => setDays(Number(event.target.value))}
                  className={inputClassName()}
                >
                  {DURATIONS.map((value) => (
                    <option key={value} value={value}>
                      {value} jours
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <Button onClick={() => void createLink()} loading={busy}>
            Créer un lien de partage
          </Button>
        </div>
      </Card>

      {loading ? <Spinner label="Chargement des liens…" /> : null}
      {!loading && links && links.length === 0 ? (
        <EmptyState
          title="Aucun lien de partage"
          description="Créez un lien pour permettre au client de choisir ses photos."
        />
      ) : null}

      {!loading && links && links.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-ink-100 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Lien</th>
                <th className="px-4 py-3 font-semibold">État</th>
                <th className="px-4 py-3 font-semibold">Expire</th>
                <th className="px-4 py-3 font-semibold">Ouvertures</th>
                <th className="px-4 py-3 font-semibold">Dernière visite</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {links.map((link) => {
                const state = linkState(link);
                return (
                  <tr key={link.id}>
                    <td className="px-4 py-3 font-mono text-xs text-ink-500">{link.url_masked}</td>
                    <td className="px-4 py-3">
                      <Badge tone={state.tone}>{state.label}</Badge>
                    </td>
                    <td className="px-4 py-3 text-ink-700">{formatDateTime(link.expires_at)}</td>
                    <td className="px-4 py-3 text-ink-700">{link.view_count}</td>
                    <td className="px-4 py-3 text-ink-700">{formatDateTime(link.last_seen_at)}</td>
                    <td className="px-4 py-3 text-right">
                      {link.revoked_at ? null : (
                        <Button
                          variant="danger"
                          size="sm"
                          disabled={busy}
                          onClick={() => void revoke(link.id)}
                        >
                          Révoquer
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {!loading && error ? <ErrorState message={error} onRetry={load} /> : null}

      <p className="mt-6 text-sm">
        <Link href={`/collections/${collectionId}`} className="text-ink-600 underline hover:no-underline">
          Revenir à la collection
        </Link>
      </p>
    </div>
  );
}
