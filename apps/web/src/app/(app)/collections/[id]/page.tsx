"use client";

import { use, useCallback, useEffect, useState } from "react";
import * as collectionsApi from "@/lib/api/resources/collections";
import * as mediaApi from "@/lib/api/resources/media";
import type { CollectionOut, MediaSummary } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { COLLECTION_STATUS_LABELS } from "@/lib/labels";
import Link from "next/link";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { AuthImage } from "@/components/media/AuthImage";
import type { CollectionStatus } from "@/lib/api/types";

const STATUS_TONE: Record<CollectionStatus, BadgeTone> = {
  draft: "neutral",
  published: "ok",
  closed: "warn",
};

function toSummary(item: Awaited<ReturnType<typeof mediaApi.get>>): MediaSummary {
  return {
    id: item.id,
    thumb_url: mediaApi.thumbUrl(item.id),
    shot_at: item.shot_at,
    ingest_status: item.ingest_status,
    attachment_status: item.attachment_status,
    shooting_id: item.shooting_id,
    is_simulated: item.is_simulated,
    duplicate_of_media_id: item.duplicate_of_media_id,
    series_id: item.series_id,
    series_member_count: null,
  };
}

export default function CollectionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const collectionId = Number(id);

  const [collection, setCollection] = useState<CollectionOut | null>(null);
  const [items, setItems] = useState<MediaSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [publishing, setPublishing] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    collectionsApi
      .get(collectionId)
      .then(async (c) => {
        setCollection(c);
        const summaries = await Promise.all(
          c.items
            .slice()
            .sort((a, b) => a.position - b.position)
            .map((i) => mediaApi.get(i.media_id).then(toSummary).catch(() => null)),
        );
        setItems(summaries.filter((s): s is MediaSummary => s != null));
        setLoading(false);
      })
      .catch((err) => {
        setError(err);
        setLoading(false);
      });
  }, [collectionId]);

  useEffect(() => {
    load();
  }, [load]);

  async function removeItem(mediaId: number) {
    setRemovingId(mediaId);
    try {
      await collectionsApi.removeItem(collectionId, mediaId);
      setItems((prev) => prev.filter((i) => i.id !== mediaId));
      setCollection((prev) => (prev ? { ...prev, items: prev.items.filter((i) => i.media_id !== mediaId) } : prev));
    } catch (err) {
      setError(err);
    } finally {
      setRemovingId(null);
    }
  }

  async function publish() {
    setPublishing(true);
    try {
      const updated = await collectionsApi.publish(collectionId);
      setCollection(updated);
      setConfirmPublish(false);
    } catch (err) {
      setError(err);
    } finally {
      setPublishing(false);
    }
  }

  if (loading) return <Spinner label="Chargement de la collection…" />;
  if (error) return <ErrorState message={friendlyErrorMessage(error)} onRetry={load} />;
  if (!collection) return null;

  return (
    <div>
      <PageHeader
        title={collection.title}
        description={collection.description ?? undefined}
        actions={
          <>
            <Badge tone={STATUS_TONE[collection.status]}>{COLLECTION_STATUS_LABELS[collection.status]}</Badge>
            {collection.status === "draft" ? (
              <Button onClick={() => setConfirmPublish(true)} disabled={items.length === 0}>
                Publier
              </Button>
            ) : (
              // Le partage n'a de sens qu'une fois la collection publiée : un lien vers une
              // collection encore en composition montrerait au client un travail inachevé.
              <Link href={`/collections/${collectionId}/share`}>
                <Button variant="secondary">Partager</Button>
              </Link>
            )}
          </>
        }
      />

      {confirmPublish ? (
        <Notice tone="warn">
          <p className="mb-2">
            Publier rendra cette collection partageable avec le client. {items.length} média
            {items.length > 1 ? "s" : ""} seront inclus. Confirmer ?
          </p>
          <div className="flex gap-2">
            <Button size="sm" loading={publishing} onClick={publish}>
              Confirmer
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirmPublish(false)}>
              Annuler
            </Button>
          </div>
        </Notice>
      ) : null}

      <div className="mt-5">
        {items.length === 0 ? (
          <EmptyState
            title="Collection vide"
            description="Ajoutez des médias depuis la recherche (« ajouter à une collection »)."
          />
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {items.map((item) => (
              <li key={item.id} className="group relative overflow-hidden rounded-lg border border-ink-100 bg-white">
                <div className="relative aspect-[3/2] w-full overflow-hidden bg-ink-100">
                  <AuthImage src={item.thumb_url} alt={`Média #${item.id}`} className="h-full w-full object-cover" />
                </div>
                <button
                  type="button"
                  onClick={() => removeItem(item.id)}
                  disabled={removingId === item.id}
                  aria-label={`Retirer le média #${item.id} de la collection`}
                  className="absolute right-1.5 top-1.5 rounded bg-ink-950/80 px-1.5 py-0.5 text-[10px] font-medium text-white opacity-0 transition-opacity hover:bg-danger-600 focus-visible:opacity-100 group-hover:opacity-100"
                >
                  {removingId === item.id ? "…" : "Retirer"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
