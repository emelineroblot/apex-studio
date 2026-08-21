"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as searchApi from "@/lib/api/resources/search";
import type { SearchParams } from "@/lib/api/resources/search";
import type { Facets, MediaSummary } from "@/lib/api/types";

export type SearchResultsState = {
  items: MediaSummary[];
  facets: Facets | null;
  total: number;
  tookMs: number | null;
  loading: boolean;
  loadingMore: boolean;
  error: unknown;
  hasMore: boolean;
  loadMore: () => void;
  reload: () => void;
};

/**
 * Pagination **réelle** (§ pièges projet : « au J1, le bouton "charger plus" n'était pas
 * câblé ») — `loadMore` accumule les pages via le curseur renvoyé par le serveur
 * (`next_cursor`), jamais un `OFFSET` recalculé côté client. Un changement de filtres
 * réinitialise entièrement la liste (nouvelle recherche), un `loadMore` l'étend.
 */
export function useSearchResults(filters: SearchParams): SearchResultsState {
  const [items, setItems] = useState<MediaSummary[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [total, setTotal] = useState(0);
  const [tookMs, setTookMs] = useState<number | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const requestId = useRef(0);
  const [reloadTick, setReloadTick] = useState(0);

  // Clé stable dérivée des filtres — évite une boucle de rechargement due à une nouvelle
  // identité d'objet à chaque rendu (le composant appelant reconstruit `filters` à chaque fois).
  const filterKey = JSON.stringify(filters);

  useEffect(() => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    searchApi
      .search({ ...filters, cursor: null })
      .then((res) => {
        if (requestId.current !== id) return;
        setItems(res.items);
        setFacets(res.facets);
        setTotal(res.total);
        setTookMs(res.took_ms);
        setNextCursor(res.next_cursor);
        setLoading(false);
      })
      .catch((err) => {
        if (requestId.current !== id) return;
        setError(err);
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, reloadTick]);

  const loadMore = useCallback(() => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    searchApi
      .search({ ...filters, cursor: nextCursor })
      .then((res) => {
        setItems((prev) => [...prev, ...res.items]);
        setFacets(res.facets);
        setTotal(res.total);
        setTookMs(res.took_ms);
        setNextCursor(res.next_cursor);
        setLoadingMore(false);
      })
      .catch((err) => {
        setError(err);
        setLoadingMore(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, nextCursor, loadingMore]);

  return {
    items,
    facets,
    total,
    tookMs,
    loading,
    loadingMore,
    error,
    hasMore: nextCursor != null,
    loadMore,
    reload: () => setReloadTick((t) => t + 1),
  };
}
