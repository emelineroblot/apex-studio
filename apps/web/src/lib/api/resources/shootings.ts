import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/shootings";
import { visibleShootingIdsForCurrentUser } from "@/lib/api/fixtures/access";
import type {
  EngagementCreate,
  EngagementImportResult,
  EngagementOut,
  Page,
  ShootingCreate,
  ShootingOut,
  ShootingPatch,
  ShootingSummary,
  StaffMember,
} from "@/lib/api/types";

export type ShootingListParams = {
  client_id?: number | null;
  from?: string | null;
  to?: string | null;
  status?: string | null;
  cursor?: string | null;
  limit?: number;
};

export async function list(params: ShootingListParams = {}): Promise<Page<ShootingSummary>> {
  if (API_MODE === "fixtures") {
    return fixtures.list(
      { ...params, visibleIds: visibleShootingIdsForCurrentUser() },
      params.cursor,
      params.limit,
    );
  }
  return apiRequest<Page<ShootingSummary>>("/shootings", { query: params });
}

export async function get(id: number): Promise<ShootingOut> {
  if (API_MODE === "fixtures") return fixtures.get(id);
  return apiRequest<ShootingOut>(`/shootings/${id}`);
}

export async function create(payload: ShootingCreate): Promise<ShootingOut> {
  if (API_MODE === "fixtures") return fixtures.create(payload);
  return apiRequest<ShootingOut>("/shootings", { method: "POST", json: payload });
}

export async function update(id: number, payload: ShootingPatch): Promise<ShootingOut> {
  if (API_MODE === "fixtures") return fixtures.update(id, payload);
  return apiRequest<ShootingOut>(`/shootings/${id}`, { method: "PATCH", json: payload });
}

export async function setStaff(id: number, userIds: number[]): Promise<StaffMember[]> {
  if (API_MODE === "fixtures") return fixtures.setStaff(id, userIds);
  const res = await apiRequest<{ staff: StaffMember[] }>(`/shootings/${id}/staff`, {
    method: "PUT",
    json: { user_ids: userIds },
  });
  return res.staff;
}

export async function listEngagements(shootingId: number): Promise<EngagementOut[]> {
  if (API_MODE === "fixtures") return fixtures.listEngagements(shootingId);
  return apiRequest<EngagementOut[]>(`/shootings/${shootingId}/engagements`);
}

export async function createEngagement(
  shootingId: number,
  payload: EngagementCreate,
): Promise<EngagementOut> {
  if (API_MODE === "fixtures") return fixtures.createEngagement(shootingId, payload);
  return apiRequest<EngagementOut>(`/shootings/${shootingId}/engagements`, {
    method: "POST",
    json: payload,
  });
}

export async function importEngagementsCsv(
  shootingId: number,
  file: File,
): Promise<EngagementImportResult> {
  if (API_MODE === "fixtures") {
    const text = await file.text();
    return fixtures.importEngagementsCsv(shootingId, text);
  }
  const form = new FormData();
  form.append("file", file);
  return apiRequest<EngagementImportResult>(`/shootings/${shootingId}/engagements:import`, {
    method: "POST",
    body: form,
  });
}
