"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import * as publicApi from "@/lib/api/resources/publicSpace";
import { ApiError } from "@/lib/api/errors";
import type { PublicCollectionRef } from "@/lib/api/types";
import {
  clearClientSession,
  getClientSession,
  isExpired,
  setClientSession,
  type ClientSession,
} from "@/lib/client/session";

export type ClientSessionState = {
  session: ClientSession | null;
  collection: PublicCollectionRef | null;
  loading: boolean;
  /** Erreur affichable telle quelle — jamais une trace technique (critère d'acceptation). */
  error: string | null;
  /** Rejoue l'échange de jeton : utilisé après un `410` pour distinguer expiration et incident. */
  reopen: () => void;
};

/**
 * Ouvre — ou rouvre — la session de l'espace client à partir du jeton de l'URL.
 *
 * Un lien mort n'est pas une erreur à afficher dans un cadre rouge : il redirige vers
 * l'écran dédié, avec le contact du studio. C'est le comportement demandé par le brief, et
 * la raison pour laquelle cette logique vit dans un hook partagé plutôt que recopiée dans
 * chaque page — un seul endroit décide de ce qu'est un lien mort.
 */
export function useClientSession(token: string): ClientSessionState {
  const router = useRouter();
  const [session, setSession] = useState<ClientSession | null>(() => getClientSession(token));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reopen = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    const existing = getClientSession(token);
    if (existing && !isExpired(existing) && attempt === 0) {
      setSession(existing);
      setLoading(false);
      return;
    }

    setLoading(true);
    publicApi
      .openSession(token)
      .then((response) => {
        if (cancelled) return;
        const opened: ClientSession = {
          accessToken: response.access_token,
          expiresAt: Date.now() + response.expires_in * 1000,
          collection: response.collection,
        };
        setClientSession(token, opened);
        setSession(opened);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        clearClientSession(token);
        setSession(null);
        setLoading(false);
        if (err instanceof ApiError && (err.status === 410 || err.status === 404)) {
          router.replace(`/c/${token}/expired`);
          return;
        }
        setError("Nous n'arrivons pas à ouvrir votre galerie pour le moment.");
      });

    return () => {
      cancelled = true;
    };
  }, [token, attempt, router]);

  return {
    session,
    collection: session?.collection ?? null,
    loading,
    error,
    reopen,
  };
}

/**
 * Traduit une erreur d'appel `/public` en action.
 *
 * Renvoie `true` si l'appelant doit s'arrêter là (redirection déjà déclenchée). Le `410`
 * arrive aussi **en cours de session** — c'est le cas d'un lien révoqué pendant que le
 * client regarde ses photos, et il ne doit pas produire un message d'erreur brut.
 */
export function handleClientApiError(err: unknown, token: string, router: ReturnType<typeof useRouter>): boolean {
  if (err instanceof ApiError && err.status === 410) {
    clearClientSession(token);
    router.replace(`/c/${token}/expired`);
    return true;
  }
  return false;
}
