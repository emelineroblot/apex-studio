"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as mediaApi from "@/lib/api/resources/media";
import type { MediaOut, MediaSummary } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { useAsync } from "@/hooks/useAsync";
import { PageHeader } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { MediaGrid } from "@/components/media/MediaGrid";
import { QuarantineCard } from "@/components/media/QuarantineCard";
import { DuplicatePairCard } from "@/components/media/DuplicatePairCard";

const TABS = [
  { id: "all", label: "Tout" },
  { id: "unattached", label: "À rattacher" },
  { id: "quarantined", label: "Quarantaine" },
  { id: "duplicates", label: "Doublons" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function LibraryPage() {
  return (
    <Suspense fallback={<Spinner label="Chargement de la bibliothèque…" />}>
      <LibraryPageContent />
    </Suspense>
  );
}

/** `useSearchParams()` exige une frontière `Suspense` (§ Next.js — sinon `next build`
 * échoue sur "missing-suspense-with-csr-bailout") — isolé dans un composant enfant. */
function LibraryPageContent() {
  const [tab, setTab] = useState<TabId>("all");
  const searchParams = useSearchParams();

  // Ouverture d'une rafale complète depuis `MediaGrid` (§ tâche 2, `GET /media?series=all`
  // — pas de paramètre `series_id` dans le contrat : on récupère la page `series=all`
  // scopée au shooting d'origine puis on filtre côté client sur `series_id`, cf.
  // `MediaGrid.seriesUrl`).
  const seriesParam = searchParams.get("series");
  const seriesId = seriesParam ? Number(seriesParam) : null;
  const shootingParam = searchParams.get("shooting");
  const shootingId = shootingParam ? Number(shootingParam) : undefined;

  const { data, loading, error, reload } = useAsync(
    () =>
      seriesId != null
        ? mediaApi.list({ series: "all", shooting_id: shootingId, limit: 100 })
        : mediaApi.list({
            limit: 100,
            unattached: tab === "unattached" ? true : undefined,
            quarantined: tab === "quarantined" ? true : undefined,
            duplicates: tab === "duplicates" ? true : undefined,
          }),
    [tab, seriesId, shootingId],
  );

  const items = useMemo(() => {
    const all = data?.items ?? [];
    if (seriesId == null) return all;
    return all.filter((m) => m.series_id === seriesId);
  }, [data, seriesId]);

  if (seriesId != null) {
    return (
      <div>
        <Link href="/library" className="text-sm text-ink-500 hover:text-accent-600">
          ← Retour à la bibliothèque
        </Link>
        <PageHeader
          title={`Série #${seriesId}`}
          description={
            items.length > 0
              ? `${items.length} cliché${items.length > 1 ? "s" : ""} de cette rafale.`
              : "Rafale groupée automatiquement par proximité temporelle et visuelle."
          }
        />
        <div className="mt-5">
          {loading ? <Spinner label="Chargement de la série…" /> : null}
          {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}
          {!loading && !error ? (
            items.length === 0 ? (
              <EmptyState
                title="Série introuvable"
                description="Cette série n'a pas (ou plus) de membres visibles depuis ce shooting."
              />
            ) : (
              <MediaGrid items={items} showSeriesBadge={false} />
            )
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Bibliothèque"
        description="Ensemble des médias ingérés — filtrez par état de traitement."
      />

      <Tabs
        items={TABS.map((t) => ({
          id: t.id,
          label: t.label,
          badge: <Badge tone="neutral">{t.id === tab ? (data?.total ?? "…") : ""}</Badge>,
        }))}
        active={tab}
        onChange={(id) => setTab(id as TabId)}
        label="Filtres de la bibliothèque"
      />

      <div className="mt-5" role="tabpanel">
        {loading ? <Spinner label="Chargement des médias…" /> : null}
        {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

        {!loading && !error ? (
          items.length === 0 ? (
            <EmptyState title={EMPTY_TITLES[tab]} description={EMPTY_DESCRIPTIONS[tab]} />
          ) : tab === "quarantined" ? (
            <QuarantineList items={items} />
          ) : tab === "duplicates" ? (
            <DuplicateList items={items} />
          ) : (
            <MediaGrid items={items} />
          )
        ) : null}

      </div>
    </div>
  );
}

const EMPTY_TITLES: Record<TabId, string> = {
  all: "Aucun média pour l'instant",
  unattached: "Aucun média à rattacher",
  quarantined: "Aucun média en quarantaine",
  duplicates: "Aucun doublon détecté",
};

const EMPTY_DESCRIPTIONS: Record<TabId, string> = {
  all: "Déposez un lot de photos pour peupler la bibliothèque.",
  unattached: "Tous les médias ingérés ont pu être rattachés automatiquement — rien à traiter.",
  quarantined: "Aucun fichier n'a déclenché le contrôle d'intégrité.",
  duplicates: "Aucun doublon exact n'a été détecté sur la page courante.",
};

function QuarantineList({ items }: { items: MediaSummary[] }) {
  const [details, setDetails] = useState<Map<number, MediaOut> | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    setDetails(null);
    Promise.all(items.map((item) => mediaApi.get(item.id)))
      .then((results) => {
        if (cancelled) return;
        setDetails(new Map(results.map((r) => [r.id, r])));
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.map((i) => i.id).join(",")]);

  if (error) return <ErrorState message={friendlyErrorMessage(error)} />;
  if (!details) return <Spinner label="Chargement des motifs de quarantaine…" />;

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => {
        const full = details.get(item.id);
        if (!full) return null;
        return <QuarantineCard key={item.id} media={full} thumbUrl={item.thumb_url} />;
      })}
    </div>
  );
}

/**
 * Un doublon **présenté avec son maître** (§ tâche 2) — `GET /media?duplicates=true` ne
 * renvoie que les doublons eux-mêmes ; le maître (`duplicate_of_media_id`) est chargé à
 * part, un seul appel par maître unique (plusieurs doublons peuvent partager le même
 * maître, ex. un 3ᵉ exemplaire identique).
 */
function DuplicateList({ items }: { items: MediaSummary[] }) {
  const [masters, setMasters] = useState<Map<number, MediaOut> | null>(null);
  const [error, setError] = useState<unknown>(null);

  const masterIds = useMemo(
    () => [...new Set(items.map((item) => item.duplicate_of_media_id).filter((id): id is number => id != null))],
    [items],
  );

  useEffect(() => {
    let cancelled = false;
    setMasters(null);
    Promise.all(masterIds.map((id) => mediaApi.get(id)))
      .then((results) => {
        if (cancelled) return;
        setMasters(new Map(results.map((r) => [r.id, r])));
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [masterIds]);

  if (error) return <ErrorState message={friendlyErrorMessage(error)} />;
  if (!masters) return <Spinner label="Chargement des maîtres…" />;

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => {
        const master = item.duplicate_of_media_id != null ? masters.get(item.duplicate_of_media_id) : undefined;
        return (
          <DuplicatePairCard
            key={item.id}
            duplicate={item}
            master={master}
            masterThumbUrl={master ? mediaApi.thumbUrl(master.id) : ""}
          />
        );
      })}
    </div>
  );
}
