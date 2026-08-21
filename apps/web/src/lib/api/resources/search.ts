import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/search";
import type { AttachmentStatus, SearchResponse, SeriesMode, SortMode } from "@/lib/api/types";

export type SearchParams = {
  q?: string | null;
  shooting_id?: number[];
  client_id?: number[];
  team_id?: number[];
  driver_id?: number[];
  car_number?: string[];
  circuit_id?: number[];
  camera_id?: number[];
  lens?: string[];
  iso_min?: number | null;
  iso_max?: number | null;
  focal_min?: number | null;
  focal_max?: number | null;
  date_from?: string | null;
  date_to?: string | null;
  status?: AttachmentStatus[];
  /** §3-N.1 / revue J2 🟠1 — `GET /search?is_simulated=` : absent = tous, `false` = réels
   * seulement, `true` = simulés seulement. Confirmé au contrat final (`schema.d.ts`,
   * intégration live J2). */
  is_simulated?: boolean | null;
  series?: SeriesMode;
  sort?: SortMode;
  cursor?: string | null;
  limit?: number;
};

/** `GET /search` (§3-K du plan) — recherche à facettes combinables, pagination keyset réelle
 * (`cursor`/`next_cursor`), `took_ms` mesuré côté serveur (ou côté moteur de fixtures, § pour
 * rester honnête plutôt que d'afficher un chiffre inventé). */
export async function search(params: SearchParams = {}): Promise<SearchResponse> {
  const limit = params.limit ?? 60;
  if (API_MODE === "fixtures") {
    return fixtures.search(params, params.cursor, limit);
  }
  return apiRequest<SearchResponse>("/search", {
    query: {
      q: params.q,
      shooting_id: params.shooting_id,
      client_id: params.client_id,
      team_id: params.team_id,
      driver_id: params.driver_id,
      car_number: params.car_number,
      circuit_id: params.circuit_id,
      camera_id: params.camera_id,
      lens: params.lens,
      iso_min: params.iso_min,
      iso_max: params.iso_max,
      focal_min: params.focal_min,
      focal_max: params.focal_max,
      date_from: params.date_from,
      date_to: params.date_to,
      status: params.status,
      is_simulated: params.is_simulated,
      series: params.series,
      sort: params.sort,
      cursor: params.cursor,
      limit,
    },
  });
}
