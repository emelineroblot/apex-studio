"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncState<T> = {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
};

/**
 * Chargement de données avec états chargement/erreur systématiques (§ exigences
 * qualité). `deps` redéclenche l'appel ; un compteur interne ignore les réponses
 * obsolètes si l'appelant relance vite (filtres tapés rapidement, par ex.).
 */
export function useAsync<T>(fn: () => Promise<T>, deps: React.DependencyList): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const requestId = useRef(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    fn()
      .then((result) => {
        if (requestId.current === id) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (requestId.current === id) {
          setError(err);
          setLoading(false);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, loading, reload };
}
