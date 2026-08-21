import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/collections";
import type { CollectionAddItemsResponse, CollectionCreate, CollectionOut, Page } from "@/lib/api/types";
import type { SearchParams } from "@/lib/api/resources/search";

export async function list(cursor?: string | null, limit = 50): Promise<Page<CollectionOut>> {
  if (API_MODE === "fixtures") return fixtures.list(cursor, limit);
  return apiRequest<Page<CollectionOut>>("/collections", { query: { cursor, limit } });
}

export async function create(payload: CollectionCreate): Promise<CollectionOut> {
  if (API_MODE === "fixtures") return fixtures.create(payload);
  return apiRequest<CollectionOut>("/collections", { method: "POST", json: payload });
}

export async function get(id: number): Promise<CollectionOut> {
  if (API_MODE === "fixtures") return fixtures.get(id);
  return apiRequest<CollectionOut>(`/collections/${id}`);
}

export type AddItemsPayload = { media_ids?: number[] | null; from_search?: SearchParams | null };

/** `POST /collections/{id}/items` — composition depuis une sélection explicite **ou** depuis
 * les paramètres d'une recherche (« ajouter les N résultats de cette recherche »). */
export async function addItems(id: number, payload: AddItemsPayload): Promise<CollectionAddItemsResponse> {
  if (API_MODE === "fixtures") {
    return fixtures.addItems(id, payload);
  }
  return apiRequest<CollectionAddItemsResponse>(`/collections/${id}/items`, { method: "POST", json: payload });
}

export async function removeItem(id: number, mediaId: number): Promise<void> {
  if (API_MODE === "fixtures") return fixtures.removeItem(id, mediaId);
  await apiRequest<void>(`/collections/${id}/items/${mediaId}`, { method: "DELETE" });
}

export async function publish(id: number): Promise<CollectionOut> {
  if (API_MODE === "fixtures") return fixtures.publish(id);
  return apiRequest<CollectionOut>(`/collections/${id}/publish`, { method: "POST" });
}
