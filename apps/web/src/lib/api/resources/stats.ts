import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/stats";
import type { AutoAttachRate } from "@/lib/api/types";

export async function autoAttachRate(
  params: { shooting_id?: number | null; from?: string | null; to?: string | null } = {},
): Promise<AutoAttachRate> {
  if (API_MODE === "fixtures") return fixtures.autoAttachRate(params);
  return apiRequest<AutoAttachRate>("/stats/auto-attach-rate", {
    // Contrat J2 (§ passe d'intégration live) : le paramètre de requête est désormais
    // `from` (plus `from_`) sur `GET /stats/auto-attach-rate` — `from` n'est pas un mot
    // réservé en TypeScript, contrairement à Python.
    query: { shooting_id: params.shooting_id, from: params.from, to: params.to },
  });
}
