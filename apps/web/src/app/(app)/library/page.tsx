"use client";

import { useEffect, useState } from "react";
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

const TABS = [
  { id: "all", label: "Tout" },
  { id: "unattached", label: "À rattacher" },
  { id: "quarantined", label: "Quarantaine" },
  { id: "duplicates", label: "Doublons" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function LibraryPage() {
  const [tab, setTab] = useState<TabId>("all");

  const { data, loading, error, reload } = useAsync(
    () =>
      mediaApi.list({
        limit: 100,
        unattached: tab === "unattached" ? true : undefined,
        quarantined: tab === "quarantined" ? true : undefined,
        duplicatesOnly: tab === "duplicates" ? true : undefined,
      }),
    [tab],
  );

  const items = data?.items ?? [];

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
