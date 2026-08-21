/**
 * Filtres de recherche ⇄ `URLSearchParams` — pure, testable (`urlState.test.ts`). Rend les
 * filtres **reflétés dans l'URL** (§ tâche 3 : « partageable, rechargeable »), avec des clés
 * courtes distinctes des noms de paramètres API (`SearchParams`), pour rester lisible dans
 * la barre d'adresse.
 */
import type { AttachmentStatus, SeriesMode, SortMode } from "@/lib/api/types";
import type { SearchFilters } from "@/lib/search/engine";

export type SearchFilterState = {
  q: string;
  shooting_id: number[];
  client_id: number[];
  team_id: number[];
  driver_id: number[];
  car_number: string[];
  circuit_id: number[];
  camera_id: number[];
  lens: string[];
  iso_min: number | null;
  iso_max: number | null;
  focal_min: number | null;
  focal_max: number | null;
  date_from: string;
  date_to: string;
  status: AttachmentStatus[];
  /** §3-N.1 / revue J2 🟠1 — `null` = tous, `false` = réels, `true` = simulés. */
  is_simulated: boolean | null;
  series: SeriesMode;
  sort: SortMode;
};

export const EMPTY_FILTERS: SearchFilterState = {
  q: "",
  shooting_id: [],
  client_id: [],
  team_id: [],
  driver_id: [],
  car_number: [],
  circuit_id: [],
  camera_id: [],
  lens: [],
  iso_min: null,
  iso_max: null,
  focal_min: null,
  focal_max: null,
  date_from: "",
  date_to: "",
  status: [],
  is_simulated: null,
  series: "collapsed",
  sort: "-shot_at",
};

const NUMBER_KEYS = ["shooting_id", "client_id", "team_id", "driver_id", "circuit_id", "camera_id"] as const;
const STRING_KEYS = ["car_number", "lens"] as const;

const URL_KEYS: Record<keyof SearchFilterState, string> = {
  q: "q",
  shooting_id: "shooting",
  client_id: "client",
  team_id: "team",
  driver_id: "driver",
  car_number: "car",
  circuit_id: "circuit",
  camera_id: "camera",
  lens: "lens",
  iso_min: "iso_min",
  iso_max: "iso_max",
  focal_min: "focal_min",
  focal_max: "focal_max",
  date_from: "from",
  date_to: "to",
  status: "status",
  is_simulated: "sim",
  series: "series",
  sort: "sort",
};

export function filtersToSearchParams(filters: SearchFilterState): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set(URL_KEYS.q, filters.q);
  for (const key of NUMBER_KEYS) {
    const values = filters[key];
    if (values.length) params.set(URL_KEYS[key], values.join(","));
  }
  for (const key of STRING_KEYS) {
    const values = filters[key];
    if (values.length) params.set(URL_KEYS[key], values.join(","));
  }
  if (filters.status.length) params.set(URL_KEYS.status, filters.status.join(","));
  if (filters.is_simulated != null) params.set(URL_KEYS.is_simulated, filters.is_simulated ? "1" : "0");
  if (filters.iso_min != null) params.set(URL_KEYS.iso_min, String(filters.iso_min));
  if (filters.iso_max != null) params.set(URL_KEYS.iso_max, String(filters.iso_max));
  if (filters.focal_min != null) params.set(URL_KEYS.focal_min, String(filters.focal_min));
  if (filters.focal_max != null) params.set(URL_KEYS.focal_max, String(filters.focal_max));
  if (filters.date_from) params.set(URL_KEYS.date_from, filters.date_from);
  if (filters.date_to) params.set(URL_KEYS.date_to, filters.date_to);
  if (filters.series !== EMPTY_FILTERS.series) params.set(URL_KEYS.series, filters.series);
  if (filters.sort !== EMPTY_FILTERS.sort) params.set(URL_KEYS.sort, filters.sort);
  return params;
}

function parseNumberList(raw: string | null): number[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((v) => Number.parseInt(v, 10))
    .filter((v) => !Number.isNaN(v));
}

function parseStringList(raw: string | null): string[] {
  if (!raw) return [];
  return raw.split(",").filter(Boolean);
}

export function searchParamsToFilters(params: URLSearchParams): SearchFilterState {
  return {
    q: params.get(URL_KEYS.q) ?? "",
    shooting_id: parseNumberList(params.get(URL_KEYS.shooting_id)),
    client_id: parseNumberList(params.get(URL_KEYS.client_id)),
    team_id: parseNumberList(params.get(URL_KEYS.team_id)),
    driver_id: parseNumberList(params.get(URL_KEYS.driver_id)),
    car_number: parseStringList(params.get(URL_KEYS.car_number)),
    circuit_id: parseNumberList(params.get(URL_KEYS.circuit_id)),
    camera_id: parseNumberList(params.get(URL_KEYS.camera_id)),
    lens: parseStringList(params.get(URL_KEYS.lens)),
    iso_min: params.has(URL_KEYS.iso_min) ? Number(params.get(URL_KEYS.iso_min)) : null,
    iso_max: params.has(URL_KEYS.iso_max) ? Number(params.get(URL_KEYS.iso_max)) : null,
    focal_min: params.has(URL_KEYS.focal_min) ? Number(params.get(URL_KEYS.focal_min)) : null,
    focal_max: params.has(URL_KEYS.focal_max) ? Number(params.get(URL_KEYS.focal_max)) : null,
    date_from: params.get(URL_KEYS.date_from) ?? "",
    date_to: params.get(URL_KEYS.date_to) ?? "",
    status: parseStringList(params.get(URL_KEYS.status)) as AttachmentStatus[],
    is_simulated: params.has(URL_KEYS.is_simulated) ? params.get(URL_KEYS.is_simulated) === "1" : null,
    series: (params.get(URL_KEYS.series) as SeriesMode | null) ?? EMPTY_FILTERS.series,
    sort: (params.get(URL_KEYS.sort) as SortMode | null) ?? EMPTY_FILTERS.sort,
  };
}

export function filtersToSearchFilters(filters: SearchFilterState): SearchFilters {
  return {
    q: filters.q || null,
    shooting_id: filters.shooting_id,
    client_id: filters.client_id,
    team_id: filters.team_id,
    driver_id: filters.driver_id,
    car_number: filters.car_number,
    circuit_id: filters.circuit_id,
    camera_id: filters.camera_id,
    lens: filters.lens,
    iso_min: filters.iso_min,
    iso_max: filters.iso_max,
    focal_min: filters.focal_min,
    focal_max: filters.focal_max,
    date_from: filters.date_from || null,
    date_to: filters.date_to || null,
    status: filters.status,
    is_simulated: filters.is_simulated,
    series: filters.series,
    sort: filters.sort,
  };
}

export function hasActiveFilters(filters: SearchFilterState): boolean {
  return JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
}
