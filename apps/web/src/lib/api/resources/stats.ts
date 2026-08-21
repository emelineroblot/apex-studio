import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/stats";
import type { AutoAttachRate } from "@/lib/api/types";

export async function autoAttachRate(
  params: { shooting_id?: number | null; from?: string | null; to?: string | null } = {},
): Promise<AutoAttachRate> {
  if (API_MODE === "fixtures") return fixtures.autoAttachRate(params);
  return apiRequest<AutoAttachRate>("/stats/auto-attach-rate", {
    query: { shooting_id: params.shooting_id, from_: params.from, to: params.to },
  });
}
