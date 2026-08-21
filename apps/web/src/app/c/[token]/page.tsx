"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import * as publicApi from "@/lib/api/resources/publicSpace";
import type { PublicMediaItem } from "@/lib/api/types";
import { useClientSession, handleClientApiError } from "@/lib/client/useClientSession";
import { ClientImage } from "@/components/client/ClientImage";
import { PhotoComment } from "@/components/client/PhotoComment";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";

/**
 * Galerie du client : cocher, commenter, puis valider.
 *
 * La sélection est **optimiste** — le clic bascule l'état tout de suite et l'appel suit.
 * Sur une grille de photos, un aller-retour serveur avant le retour visuel donne
 * l'impression que rien ne réagit ; l'échec est rare, et il est rattrapé en remettant la
 * case dans son état d'origine avec un message.
 */
export default function ClientGalleryPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const router = useRouter();
  const { session, collection, loading: sessionLoading, error: sessionError } = useClientSession(token);

  const [items, setItems] = useState<PublicMediaItem[] | null>(null);
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [validated, setValidated] = useState(false);

  const accessToken = session?.accessToken ?? null;

  const load = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const [collectionPage, selection] = await Promise.all([
        publicApi.getCollection(accessToken, { selected_only: selectedOnly, limit: 100 }),
        publicApi.getSelection(accessToken),
      ]);
      setItems(collectionPage.items);
      setValidated(selection.status === "validated");
      setFailure(null);
    } catch (err) {
      if (handleClientApiError(err, token, router)) return;
      setFailure("Vos photos n'ont pas pu être chargées.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, selectedOnly, token, router]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedCount = useMemo(
    () => (items ?? []).filter((item) => item.selected).length,
    [items],
  );

  function patchItem(mediaId: number, patch: Partial<PublicMediaItem>) {
    setItems((current) =>
      (current ?? []).map((item) => (item.media_id === mediaId ? { ...item, ...patch } : item)),
    );
  }

  async function toggle(item: PublicMediaItem) {
    if (!accessToken || validated) return;
    const wasSelected = item.selected;
    patchItem(item.media_id, { selected: !wasSelected });
    try {
      if (wasSelected) {
        await publicApi.deselectMedia(accessToken, item.media_id);
        patchItem(item.media_id, { comment: null });
      } else {
        await publicApi.selectMedia(accessToken, item.media_id, item.comment);
      }
      setFailure(null);
    } catch (err) {
      if (handleClientApiError(err, token, router)) return;
      // Retour à l'état réel : une case qui reste cochée alors que le serveur ne l'a pas
      // enregistrée ferait croire au client qu'il recevra une photo qu'il n'aura pas.
      patchItem(item.media_id, { selected: wasSelected });
      setFailure("Votre choix n'a pas pu être enregistré. Réessayez dans un instant.");
    }
  }

  async function saveComment(item: PublicMediaItem, comment: string | null) {
    if (!accessToken) return;
    await publicApi.selectMedia(accessToken, item.media_id, comment);
    patchItem(item.media_id, { comment, selected: true });
  }

  if (sessionLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Ouverture de votre galerie…" />
      </div>
    );
  }

  if (sessionError || !session || !collection) {
    return (
      <div className="mx-auto max-w-lg px-4 py-24">
        <ErrorState message={sessionError ?? "Galerie indisponible."} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 pb-32 pt-10">
      <header className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
          {collection.studio_name}
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-ink-900">{collection.title}</h1>
        {collection.description ? (
          <p className="mt-2 max-w-2xl text-sm text-ink-600">{collection.description}</p>
        ) : null}
      </header>

      {validated ? (
        <Notice tone="ok">
          <p>
            Votre sélection est validée : elle ne peut plus être modifiée.{" "}
            <Link href={`/c/${token}/validate`} className="font-medium underline hover:no-underline">
              Suivre la préparation de votre livraison
            </Link>
            .
          </p>
        </Notice>
      ) : null}

      {failure ? (
        <div className="mt-4">
          <Notice tone="danger" onDismiss={() => setFailure(null)}>
            {failure}
          </Notice>
        </div>
      ) : null}

      <div className="mt-6 flex items-center gap-3">
        <Button
          variant={selectedOnly ? "primary" : "secondary"}
          size="sm"
          onClick={() => setSelectedOnly((value) => !value)}
          aria-pressed={selectedOnly}
        >
          {selectedOnly ? "Toutes les photos" : "Ma sélection uniquement"}
        </Button>
        <span className="text-sm text-ink-500">
          {collection.item_count} photo{collection.item_count > 1 ? "s" : ""} au total
        </span>
      </div>

      {loading ? <Spinner label="Chargement des photos…" /> : null}

      {!loading && items && items.length === 0 ? (
        <EmptyState
          title={selectedOnly ? "Aucune photo sélectionnée" : "Aucune photo"}
          description={
            selectedOnly
              ? "Cochez les photos qui vous intéressent pour les retrouver ici."
              : "Votre galerie est vide pour le moment."
          }
        />
      ) : null}

      {!loading && items && items.length > 0 ? (
        <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <li
              key={item.media_id}
              className={clsx(
                "overflow-hidden rounded-xl border bg-white transition-shadow",
                item.selected ? "border-accent-600 shadow-md" : "border-ink-200",
              )}
            >
              <button
                type="button"
                onClick={() => void toggle(item)}
                disabled={validated}
                aria-pressed={item.selected}
                aria-label={`${item.selected ? "Retirer" : "Choisir"} la photo ${item.media_id}`}
                className="relative block w-full disabled:cursor-not-allowed"
              >
                <ClientImage
                  accessToken={session.accessToken}
                  path={item.thumb_url}
                  alt={`Photo ${item.car_numbers.join(", ") || item.media_id}`}
                  className="aspect-[3/2] w-full object-cover"
                />
                <span
                  className={clsx(
                    "absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full border-2 text-sm font-bold",
                    item.selected
                      ? "border-accent-600 bg-accent-600 text-white"
                      : "border-white/80 bg-black/30 text-transparent",
                  )}
                  aria-hidden="true"
                >
                  ✓
                </span>
              </button>

              <div className="px-3 pb-3 pt-2">
                <p className="text-xs text-ink-500">
                  {item.car_numbers.length > 0 ? (
                    <span className="font-semibold text-ink-700">
                      N° {item.car_numbers.join(" · ")}
                    </span>
                  ) : (
                    <span>Numéro non identifié</span>
                  )}
                  {item.shot_at ? (
                    <span> — {new Date(item.shot_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</span>
                  ) : null}
                </p>
                {item.selected ? (
                  <PhotoComment
                    value={item.comment}
                    disabled={validated}
                    onSave={(comment) => saveComment(item, comment)}
                  />
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {/* Compteur flottant : sur une longue grille, le bouton de validation doit rester
          atteignable sans remonter en haut de page. */}
      {!validated ? (
        <div className="fixed inset-x-0 bottom-0 border-t border-ink-200 bg-white/95 px-4 py-3 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
            <p className="text-sm text-ink-700">
              <strong className="text-ink-900">{selectedCount}</strong> photo
              {selectedCount > 1 ? "s" : ""} sélectionnée{selectedCount > 1 ? "s" : ""}
            </p>
            <Link href={`/c/${token}/validate`} aria-disabled={selectedCount === 0}>
              <Button disabled={selectedCount === 0}>Valider ma sélection</Button>
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
