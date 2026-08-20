import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/engagements";
import type { EngagementOut, EngagementPatch } from "@/lib/api/types";

export async function update(id: number, payload: EngagementPatch): Promise<EngagementOut> {
  if (API_MODE === "fixtures") return fixtures.update(id, payload);
  return apiRequest<EngagementOut>(`/engagements/${id}`, { method: "PATCH", json: payload });
}

export async function remove(id: number): Promise<void> {
  if (API_MODE === "fixtures") return fixtures.remove(id);
  return apiRequest<void>(`/engagements/${id}`, { method: "DELETE" });
}
