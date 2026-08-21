/**
 * Client HTTP réel (mode "live") — fetch typé, en-tête `Authorization: Bearer <jwt>`,
 * corps d'erreur uniforme (`ApiError`). Utilisé par `lib/api/resources/**` quand
 * `NEXT_PUBLIC_API_MODE=live`. En mode "fixtures" (par défaut tant que le backend répond
 * `501`), ces mêmes fonctions de ressources appellent `lib/api/fixtures/**` à la place —
 * aucun composant d'écran n'importe jamais ce fichier directement.
 */
import { API_BASE_URL, API_PREFIX } from "@/lib/env";
import { getToken, clearSession } from "@/lib/auth/session";
import { ApiError, type ApiErrorBody } from "@/lib/api/errors";

type QueryValue = string | number | boolean | undefined | null;

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /**
   * Une valeur `Array` produit **une clé répétée** (`shooting_id=1&shooting_id=2`) — c'est
   * la convention FastAPI/`Query(list[int])` du contrat J2 (§ facettes multi-sélection) :
   * `URLSearchParams.append`, jamais `.set`, sinon seule la dernière valeur survivrait.
   */
  query?: Record<string, QueryValue | QueryValue[]>;
  json?: unknown;
  body?: BodyInit;
  headers?: Record<string, string>;
  /** `true` pour les endpoints `/public/**` (jeton de partage, pas le JWT interne). */
  skipAuth?: boolean;
};

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${API_PREFIX}${path}`, API_BASE_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const item of value) {
          if (item === undefined || item === null || item === "") continue;
          url.searchParams.append(key, String(item));
        }
        continue;
      }
      if (value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parseErrorBody(response: Response): Promise<ApiErrorBody> {
  try {
    const data = await response.json();
    if (data && typeof data === "object" && "message" in data) {
      return data as ApiErrorBody;
    }
    return { code: "http_error", message: response.statusText };
  } catch {
    return { code: "http_error", message: response.statusText || "Erreur réseau" };
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, json, body, headers = {}, skipAuth = false } = options;

  const finalHeaders: Record<string, string> = { ...headers };
  if (json !== undefined) finalHeaders["Content-Type"] = "application/json";
  if (!skipAuth) {
    const token = getToken();
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers: finalHeaders,
      body: json !== undefined ? JSON.stringify(json) : body,
    });
  } catch {
    throw new ApiError(0, {
      code: "network_error",
      message: "Impossible de joindre le serveur. Vérifiez votre connexion.",
    });
  }

  if (response.status === 204) return undefined as T;

  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    if (response.status === 401 && !skipAuth) clearSession();
    throw new ApiError(response.status, errorBody);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Fichier binaire authentifié (vignette, aperçu, HD) — accès toujours médié par le backend. */
export async function apiFetchBlob(
  path: string,
  options: { skipAuth?: boolean } = {},
): Promise<Blob> {
  const finalHeaders: Record<string, string> = {};
  if (!options.skipAuth) {
    const token = getToken();
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(buildUrl(path), { headers: finalHeaders });
  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    throw new ApiError(response.status, errorBody);
  }
  return response.blob();
}
