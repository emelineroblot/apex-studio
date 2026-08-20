import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/clients";
import type { ClientCreate, ClientOut, ClientUpdate, Page } from "@/lib/api/types";

export async function list(params: { cursor?: string | null; limit?: number } = {}): Promise<Page<ClientOut>> {
  if (API_MODE === "fixtures") return fixtures.list(params.cursor, params.limit);
  return apiRequest<Page<ClientOut>>("/clients", { query: params });
}

export async function get(id: number): Promise<ClientOut> {
  if (API_MODE === "fixtures") return fixtures.get(id);
  return apiRequest<ClientOut>(`/clients/${id}`);
}

export async function create(payload: ClientCreate): Promise<ClientOut> {
  if (API_MODE === "fixtures") return fixtures.create(payload);
  return apiRequest<ClientOut>("/clients", { method: "POST", json: payload });
}

export async function update(id: number, payload: ClientUpdate): Promise<ClientOut> {
  if (API_MODE === "fixtures") return fixtures.update(id, payload);
  return apiRequest<ClientOut>(`/clients/${id}`, { method: "PATCH", json: payload });
}

export async function remove(id: number): Promise<void> {
  if (API_MODE === "fixtures") return fixtures.remove(id);
  return apiRequest<void>(`/clients/${id}`, { method: "DELETE" });
}
