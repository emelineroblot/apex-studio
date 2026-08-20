import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/circuits";
import type { CircuitCreate, CircuitOut, Page } from "@/lib/api/types";

export async function list(params: { cursor?: string | null; limit?: number } = {}): Promise<Page<CircuitOut>> {
  if (API_MODE === "fixtures") return fixtures.list(params.cursor, params.limit);
  return apiRequest<Page<CircuitOut>>("/circuits", { query: params });
}

export async function get(id: number): Promise<CircuitOut> {
  if (API_MODE === "fixtures") return fixtures.get(id);
  return apiRequest<CircuitOut>(`/circuits/${id}`);
}

export async function create(payload: CircuitCreate): Promise<CircuitOut> {
  if (API_MODE === "fixtures") return fixtures.create(payload);
  return apiRequest<CircuitOut>("/circuits", { method: "POST", json: payload });
}
