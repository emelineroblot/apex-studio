/**
 * Session de l'espace client — **délibérément séparée** de `lib/auth/session.ts`.
 *
 * Rien n'est partagé avec le back-office : ni la clé de stockage, ni le jeton, ni les
 * fonctions. C'est le pendant côté navigateur du cloisonnement que le backend impose côté
 * serveur (§3-L.3, routeur `/public` dédié) — un client qui ouvre un lien de partage ne
 * doit jamais pouvoir hériter d'une session studio restée ouverte dans le même navigateur,
 * ni l'inverse.
 *
 * Le jeton de session dure 30 minutes ; le jeton long du lien, lui, reste dans l'URL et
 * sert à en réobtenir un. On garde donc les deux : le court pour les requêtes, le long
 * pour renouveler sans redemander quoi que ce soit au visiteur.
 */
import type { PublicCollectionRef } from "@/lib/api/types";

const STORAGE_PREFIX = "apex.client.v1:";

export type ClientSession = {
  /** JWT de portée `client`, 30 minutes. */
  accessToken: string;
  /** Instant d'expiration en millisecondes epoch — sert à renouveler avant l'échec. */
  expiresAt: number;
  collection: PublicCollectionRef;
};

/** Une session par lien : deux collections ouvertes dans deux onglets ne se marchent pas
 * dessus, et fermer l'une ne déconnecte pas l'autre. */
function storageKey(token: string): string {
  return `${STORAGE_PREFIX}${token.slice(0, 12)}`;
}

const memory = new Map<string, ClientSession>();

export function getClientSession(token: string): ClientSession | null {
  const cached = memory.get(token);
  if (cached) return cached;
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(storageKey(token));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ClientSession;
    memory.set(token, parsed);
    return parsed;
  } catch {
    // `sessionStorage` indisponible (navigation privée stricte) : la session reste en
    // mémoire pour la durée de l'onglet, dégradé acceptable.
    return null;
  }
}

export function setClientSession(token: string, session: ClientSession): void {
  memory.set(token, session);
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(storageKey(token), JSON.stringify(session));
  } catch {
    /* voir ci-dessus */
  }
}

export function clearClientSession(token: string): void {
  memory.delete(token);
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(storageKey(token));
  } catch {
    /* voir ci-dessus */
  }
}

/**
 * Marge avant expiration au-delà de laquelle on renouvelle sans attendre l'erreur.
 * Trente secondes : assez pour couvrir une requête lente, assez peu pour ne pas
 * renouveler à chaque navigation.
 */
const RENEW_MARGIN_MS = 30_000;

export function isExpired(session: ClientSession): boolean {
  return Date.now() >= session.expiresAt - RENEW_MARGIN_MS;
}
