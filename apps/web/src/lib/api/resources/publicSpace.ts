/**
 * Appels de l'espace client (`/public/**`).
 *
 * Toutes les requêtes passent `skipAuth: true` et portent **explicitement** le jeton de
 * session client : jamais `getToken()`, qui renverrait la session studio si l'utilisatrice
 * a le back-office ouvert dans le même navigateur. Le cloisonnement du backend n'aurait
 * aucun intérêt si le frontend mélangeait les deux ici.
 *
 * `openSession` est la seule fonction sans jeton — c'est la porte d'entrée.
 */
import { API_MODE } from "@/lib/env";
import { apiRequest, apiFetchBlob } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/publicSpace";
import type {
  PublicCollectionResponse,
  PublicDeliveryStatusResponse,
  PublicSelectionItemResponse,
  PublicSelectionResponse,
  PublicSelectionValidateResponse,
  PublicSessionResponse,
} from "@/lib/api/types";

function auth(accessToken: string): { skipAuth: true; headers: Record<string, string> } {
  return { skipAuth: true, headers: { Authorization: `Bearer ${accessToken}` } };
}

/** `POST /public/session` — échange le jeton long du lien contre une session de 30 min. */
export async function openSession(token: string): Promise<PublicSessionResponse> {
  if (API_MODE === "fixtures") return fixtures.openSession(token);
  return apiRequest<PublicSessionResponse>("/public/session", {
    method: "POST",
    json: { token },
    skipAuth: true,
  });
}

export async function getCollection(
  accessToken: string,
  params: { cursor?: string | null; limit?: number; selected_only?: boolean } = {},
): Promise<PublicCollectionResponse> {
  if (API_MODE === "fixtures") return fixtures.getCollection(params);
  return apiRequest<PublicCollectionResponse>("/public/collection", {
    query: {
      cursor: params.cursor,
      limit: params.limit,
      selected_only: params.selected_only,
    },
    ...auth(accessToken),
  });
}

export async function selectMedia(
  accessToken: string,
  mediaId: number,
  comment: string | null,
): Promise<PublicSelectionItemResponse> {
  if (API_MODE === "fixtures") return fixtures.selectMedia(mediaId, comment);
  return apiRequest<PublicSelectionItemResponse>(`/public/selection/items/${mediaId}`, {
    method: "PUT",
    json: { comment },
    ...auth(accessToken),
  });
}

export async function deselectMedia(accessToken: string, mediaId: number): Promise<void> {
  if (API_MODE === "fixtures") return fixtures.deselectMedia(mediaId);
  await apiRequest<void>(`/public/selection/items/${mediaId}`, {
    method: "DELETE",
    ...auth(accessToken),
  });
}

export async function getSelection(accessToken: string): Promise<PublicSelectionResponse> {
  if (API_MODE === "fixtures") return fixtures.getSelection();
  return apiRequest<PublicSelectionResponse>("/public/selection", auth(accessToken));
}

export async function validateSelection(
  accessToken: string,
): Promise<PublicSelectionValidateResponse> {
  if (API_MODE === "fixtures") return fixtures.validateSelection();
  return apiRequest<PublicSelectionValidateResponse>("/public/selection/validate", {
    method: "POST",
    ...auth(accessToken),
  });
}

export async function getDelivery(
  accessToken: string,
): Promise<PublicDeliveryStatusResponse> {
  if (API_MODE === "fixtures") return fixtures.getDelivery();
  return apiRequest<PublicDeliveryStatusResponse>("/public/delivery", auth(accessToken));
}

/**
 * L'archive : récupérée en `Blob` puis remise au navigateur.
 *
 * Un `<a href>` direct ne peut pas porter d'en-tête `Authorization`, et le stockage objet
 * n'est jamais exposé en direct (`AGENTS.md`) — il n'existe donc pas d'URL publique vers
 * laquelle pointer. Le coût est que le fichier transite par la mémoire du navigateur : à
 * l'échelle d'une collection de démonstration (200 photos au plus), c'est acceptable.
 */
export async function downloadArchive(accessToken: string): Promise<Blob> {
  if (API_MODE === "fixtures") return fixtures.downloadArchive();
  return apiFetchBlob("/public/delivery/archive", {
    skipAuth: true,
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

/** Vignette ou aperçu filigrané — même raison que ci-dessus : l'accès est médié. */
export async function fetchImage(accessToken: string, path: string): Promise<Blob> {
  if (API_MODE === "fixtures") return fixtures.fetchImage(path);
  return apiFetchBlob(path, {
    skipAuth: true,
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
