/**
 * Session — JWT en mémoire + `sessionStorage` (Décision I du plan, §3-I) : jamais de
 * cookie (cross-origin front/API, pas de `SameSite`/`credentials` à gérer). Risque XSS
 * accepté et documenté : données fictives, réinitialisées chaque nuit, pas de production.
 */
import type { Role, UserOut } from "@/lib/api/types";

const STORAGE_KEY = "apex.session.v1";

export type Session = {
  token: string;
  user: UserOut;
};

let memorySession: Session | null = null;
const listeners = new Set<(session: Session | null) => void>();

function persist(session: Session | null) {
  if (typeof window === "undefined") return;
  try {
    if (session) {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } else {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // sessionStorage indisponible (navigation privée stricte) : la session reste en
    // mémoire pour l'onglet courant, c'est un dégradé acceptable pour une démo.
  }
}

function hydrate(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function getSession(): Session | null {
  if (memorySession) return memorySession;
  memorySession = hydrate();
  return memorySession;
}

export function setSession(session: Session): void {
  memorySession = session;
  persist(session);
  listeners.forEach((fn) => fn(session));
}

export function clearSession(): void {
  memorySession = null;
  persist(null);
  listeners.forEach((fn) => fn(null));
}

export function getToken(): string | null {
  return getSession()?.token ?? null;
}

export function getCurrentUser(): UserOut | null {
  return getSession()?.user ?? null;
}

export function hasRole(role: Role): boolean {
  return getCurrentUser()?.role === role;
}

export function subscribeSession(fn: (session: Session | null) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
