import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/drivers";
import type { DriverCreate, DriverOut, Page } from "@/lib/api/types";

export async function list(params: { cursor?: string | null; limit?: number } = {}): Promise<Page<DriverOut>> {
  if (API_MODE === "fixtures") return fixtures.list(params.cursor, params.limit);
  return apiRequest<Page<DriverOut>>("/drivers", { query: params });
}

export async function get(id: number): Promise<DriverOut> {
  if (API_MODE === "fixtures") return fixtures.get(id);
  return apiRequest<DriverOut>(`/drivers/${id}`);
}

export async function create(payload: DriverCreate): Promise<DriverOut> {
  if (API_MODE === "fixtures") return fixtures.create(payload);
  return apiRequest<DriverOut>("/drivers", { method: "POST", json: payload });
}
