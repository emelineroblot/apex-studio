"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSearchResults } from "@/hooks/useSearchResults";
import { filtersToSearchFilters, filtersToSearchParams, hasActiveFilters, searchParamsToFilters, type SearchFilterState } from "@/lib/search/urlState";
import { toggleWithRange } from "@/lib/search/selection";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { MediaGrid } from "@/components/media/MediaGrid";
import { FacetPanel } from "@/components/facets/FacetPanel";
import { CollectionComposerModal, type CompositionSource } from "@/components/collections/CollectionComposerModal";

export default function SearchPage() {
  return (
    <Suspense fallback={<Spinner label="Chargement de la recherche…" />}>
      <SearchPageContent />
    </Suspense>
  );
}

/** `useSearchParams()` exige une frontière `Suspense` (même contrainte que `/library`, §
 * `implementation.md` J1). */
function SearchPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<SearchFilterState>(() => searchParamsToFilters(searchParams));
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [lastIndex, setLastIndex] = useState<number | null>(null);
  const [composerSource, setComposerSource] = useState<CompositionSource | null>(null);

  const apiFilters = useMemo(() => filtersToSearchFilters(filters), [filters]);
  const { items, facets, total, tookMs, loading, loadingMore, error, hasMore, loadMore, reload } = useSearchResults({
    ...apiFilters,
    limit: 60,
  });

  function applyPatch(patch: Partial<SearchFilterState>) {
    const next = { ...filters, ...patch };
    setFilters(next);
    setSelectedIds(new Set());
    setLastIndex(null);
    const params = filtersToSearchParams(next);
    router.replace(params.size > 0 ? `/search?${params.toString()}` : "/search", { scroll: false });
  }

  function clearFilters() {
    applyPatch({
      q: "",
      shooting_id: [],
      client_id: [],
      team_id: [],
      driver_id: [],
      car_number: [],
      circuit_id: [],
      camera_id: [],
      lens: [],
      iso_min: null,
      iso_max: null,
      focal_min: null,
      focal_max: null,
      date_from: "",
      date_to: "",
      status: [],
      is_simulated: null,
    });
  }

  function handleToggleSelect(index: number, event: { shiftKey: boolean }) {
    const ids = items.map((i) => i.id);
    const { next, lastIndex: newLastIndex } = toggleWithRange(selectedIds, ids, index, lastIndex, event.shiftKey);
    setSelectedIds(next);
    setLastIndex(newLastIndex);
  }

  return (
    <div>
      <PageHeader
        title="Recherche"
        description={
          tookMs != null
            ? `${total.toLocaleString("fr-FR")} résultat${total > 1 ? "s" : ""} · ${tookMs} ms`
            : "Combinez client, shooting, circuit, date, pilote, écurie, numéro, boîtier, objectif, ISO, focale et statut."
        }
        actions={
          <>
            {hasActiveFilters(filters) ? (
              <Button variant="secondary" size="sm" onClick={clearFilters}>
                Réinitialiser les filtres
              </Button>
            ) : null}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => applyPatch({ series: filters.series === "collapsed" ? "all" : "collapsed" })}
            >
              {filters.series === "collapsed" ? "Afficher toutes les photos" : "Grouper les rafales"}
            </Button>
          </>
        }
      />

      {selectedIds.size > 0 ? (
        <Notice tone="accent" onDismiss={() => setSelectedIds(new Set())}>
          <div className="flex flex-wrap items-center gap-3">
            <span>
              {selectedIds.size} média{selectedIds.size > 1 ? "s" : ""} sélectionné{selectedIds.size > 1 ? "s" : ""}.
            </span>
            <Button size="sm" onClick={() => setComposerSource({ type: "selection", mediaIds: [...selectedIds] })}>
              Ajouter à une collection
            </Button>
          </div>
        </Notice>
      ) : null}

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[16rem_1fr]">
        <aside>
          {facets ? (
            <FacetPanel facets={facets} filters={filters} onChange={applyPatch} />
          ) : (
            <div className="rounded-xl border border-ink-100 bg-white p-4">
              <Spinner label="Chargement des facettes…" />
            </div>
          )}
        </aside>

        <div>
          {total > 0 ? (
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs text-ink-500">
                {items.length} sur {total.toLocaleString("fr-FR")} affichés
              </p>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setComposerSource({ type: "search", filters: apiFilters, resultCount: total })}
              >
                Ajouter les {total} résultats à une collection
              </Button>
            </div>
          ) : null}

          {loading ? <Spinner label="Recherche en cours…" /> : null}
          {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

          {!loading && !error ? (
            items.length === 0 ? (
              <EmptyState
                title="Aucun résultat"
                description="Élargissez les filtres ou vérifiez l'orthographe de la recherche plein texte."
              />
            ) : (
              <>
                <MediaGrid
                  items={items}
                  selectable
                  selectedIds={selectedIds}
                  onToggleSelect={handleToggleSelect}
                />
                {hasMore ? (
                  <div className="mt-5 flex justify-center">
                    <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
                      Charger plus
                    </Button>
                  </div>
                ) : null}
              </>
            )
          ) : null}
        </div>
      </div>

      <CollectionComposerModal open={composerSource != null} onClose={() => setComposerSource(null)} source={composerSource} />
    </div>
  );
}
