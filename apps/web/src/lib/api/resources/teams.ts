import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/teams";
import type { Page, TeamCreate, TeamOut } from "@/lib/api/types";

export async function list(params: { cursor?: string | null; limit?: number } = {}): Promise<Page<TeamOut>> {
  if (API_MODE === "fixtures") return fixtures.list(params.cursor, params.limit);
  return apiRequest<Page<TeamOut>>("/teams", { query: params });
}

export async function get(id: number): Promise<TeamOut> {
  if (API_MODE === "fixtures") return fixtures.get(id);
  return apiRequest<TeamOut>(`/teams/${id}`);
}

export async function create(payload: TeamCreate): Promise<TeamOut> {
  if (API_MODE === "fixtures") return fixtures.create(payload);
  return apiRequest<TeamOut>("/teams", { method: "POST", json: payload });
}
