/**
 * Moteur de recherche à facettes — logique **pure**, sans I/O, testable sans navigateur ni
 * réseau (`engine.test.ts`). Rejoue côté client la même règle de justesse que le backend
 * (`services/api/src/apex/services/facets.py`, § plan Décision K.2) : le compteur d'une
 * facette **multi-sélection** (case à cocher) s'évalue en appliquant tous les filtres
 * **sauf le sien** ; les facettes **mono-sélection** (plages ISO/focale, dates) s'évaluent
 * sur le jeu filtré complet, filtre inclus. C'est délibérément la même fonction qui sert
 * `lib/api/fixtures/search.ts` (mode démo) — en mode live, c'est `GET /search` qui fait
 * autorité, ce module ne recalcule jamais rien côté client dans ce cas.
 *
 * Utilisé par `fixtures/search.ts` avec un jeu de plusieurs centaines d'entrées synthétiques
 * (`fixtures/searchIndex.ts`) — le volume réel (~8 000, § brief) est un sujet de performance
 * backend (`tests/search/test_perf.py`), pas de correction frontend : ce module doit rester
 * correct à n'importe quelle échelle, pas rapide à 8 000 lignes en JS non indexé.
 */
import type {
  AttachmentStatus,
  FacetBucket,
  FacetStatusTerm,
  FacetTerm,
  Facets,
  MediaSummary,
  SeriesMode,
  SortMode,
} from "@/lib/api/types";

export type SearchIndexEntry = {
  id: number;
  thumb_url: string;
  shot_at: string | null;
  ingest_status: MediaSummary["ingest_status"];
  attachment_status: AttachmentStatus;
  shooting_id: number | null;
  client_id: number | null;
  circuit_id: number | null;
  camera_id: number | null;
  lens: string | null;
  iso: number | null;
  focal_length: number | null;
  team_ids: number[];
  driver_ids: number[];
  car_numbers: string[];
  caption: string | null;
  keywords: string[];
  series_id: number | null;
  series_member_count: number | null;
  is_series_representative: boolean;
  duplicate_of_media_id: number | null;
  is_simulated: boolean;
};

export type SearchFilters = {
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
  /** `media.is_simulated` (§3-N.1) — mono-sélection à 3 états : `null`/absent = tous,
   * `false` = réels seulement, `true` = simulés seulement. Revue J2 🟠1 : la colonne était
   * projetée sans être filtrable. */
  is_simulated?: boolean | null;
  series?: SeriesMode;
  sort?: SortMode;
};

export type LabelResolvers = {
  shooting(id: number): string | null;
  client(id: number): string | null;
  team(id: number): string | null;
  driver(id: number): string | null;
  circuit(id: number): string | null;
  camera(id: number): string | null;
};

/** Bornes métier fixées (§3-K.2 du plan) — pas de configuration, comme le backend. */
export const ISO_BREAKPOINTS = [100, 400, 1600, 6400];
export const FOCAL_BREAKPOINTS = [24, 70, 200, 400];

type Clause = {
  /** Nom de la facette **multi-sélection** que cette clause représente, ou `null` si la
   * clause ne doit jamais être exclue (plein texte, doublons, séries collapsées). */
  facet: FacetKey | null;
  test: (entry: SearchIndexEntry) => boolean;
};

export type FacetKey =
  | "shooting"
  | "client"
  | "team"
  | "driver"
  | "car_number"
  | "circuit"
  | "camera"
  | "lens"
  | "status";

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function matchesFullText(entry: SearchIndexEntry, q: string): boolean {
  const terms = normalize(q).split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const haystack = normalize(
    [entry.caption ?? "", ...(entry.keywords ?? []), ...entry.car_numbers].join(" "),
  );
  return terms.every((term) => haystack.includes(term));
}

function buildClauses(filters: SearchFilters): Clause[] {
  const clauses: Clause[] = [];

  if (filters.q) {
    const q = filters.q;
    clauses.push({ facet: null, test: (e) => matchesFullText(e, q) });
  }
  if (filters.shooting_id?.length) {
    const set = new Set(filters.shooting_id);
    clauses.push({ facet: "shooting", test: (e) => e.shooting_id != null && set.has(e.shooting_id) });
  }
  if (filters.client_id?.length) {
    const set = new Set(filters.client_id);
    clauses.push({ facet: "client", test: (e) => e.client_id != null && set.has(e.client_id) });
  }
  if (filters.team_id?.length) {
    const set = new Set(filters.team_id);
    clauses.push({ facet: "team", test: (e) => e.team_ids.some((id) => set.has(id)) });
  }
  if (filters.driver_id?.length) {
    const set = new Set(filters.driver_id);
    clauses.push({ facet: "driver", test: (e) => e.driver_ids.some((id) => set.has(id)) });
  }
  if (filters.car_number?.length) {
    const set = new Set(filters.car_number);
    clauses.push({ facet: "car_number", test: (e) => e.car_numbers.some((n) => set.has(n)) });
  }
  if (filters.circuit_id?.length) {
    const set = new Set(filters.circuit_id);
    clauses.push({ facet: "circuit", test: (e) => e.circuit_id != null && set.has(e.circuit_id) });
  }
  if (filters.camera_id?.length) {
    const set = new Set(filters.camera_id);
    clauses.push({ facet: "camera", test: (e) => e.camera_id != null && set.has(e.camera_id) });
  }
  if (filters.lens?.length) {
    const set = new Set(filters.lens);
    clauses.push({ facet: "lens", test: (e) => e.lens != null && set.has(e.lens) });
  }
  if (filters.status?.length) {
    const set = new Set(filters.status);
    clauses.push({ facet: "status", test: (e) => set.has(e.attachment_status) });
  }
  if (filters.is_simulated != null) {
    const wantSimulated = filters.is_simulated;
    clauses.push({ facet: null, test: (e) => e.is_simulated === wantSimulated });
  }
  if (filters.iso_min != null) {
    const min = filters.iso_min;
    clauses.push({ facet: null, test: (e) => e.iso != null && e.iso >= min });
  }
  if (filters.iso_max != null) {
    const max = filters.iso_max;
    clauses.push({ facet: null, test: (e) => e.iso != null && e.iso <= max });
  }
  if (filters.focal_min != null) {
    const min = filters.focal_min;
    clauses.push({ facet: null, test: (e) => e.focal_length != null && e.focal_length >= min });
  }
  if (filters.focal_max != null) {
    const max = filters.focal_max;
    clauses.push({ facet: null, test: (e) => e.focal_length != null && e.focal_length <= max });
  }
  if (filters.date_from) {
    const from = filters.date_from;
    clauses.push({ facet: null, test: (e) => e.shot_at != null && e.shot_at.slice(0, 10) >= from });
  }
  if (filters.date_to) {
    const to = filters.date_to;
    clauses.push({ facet: null, test: (e) => e.shot_at != null && e.shot_at.slice(0, 10) <= to });
  }
  // Doublons toujours exclus (§ pièges projet — critère universel, pas seulement `/media`).
  clauses.push({ facet: null, test: (e) => e.duplicate_of_media_id == null });
  if ((filters.series ?? "collapsed") === "collapsed") {
    clauses.push({ facet: null, test: (e) => e.series_id == null || e.is_series_representative });
  }

  return clauses;
}

function applyClauses(pool: SearchIndexEntry[], clauses: Clause[], except: FacetKey | null): SearchIndexEntry[] {
  const active = clauses.filter((c) => c.facet !== except);
  return pool.filter((entry) => active.every((c) => c.test(entry)));
}

/** Tous les résultats correspondant aux filtres, **non paginés** — utilisé par la
 * composition de collection « ajouter les N résultats de cette recherche »
 * (`POST /collections/{id}/items {from_search}`), qui doit porter sur l'ensemble du
 * résultat, pas seulement la page actuellement affichée. */
export function filterEntries(pool: SearchIndexEntry[], filters: SearchFilters): SearchIndexEntry[] {
  return applyClauses(pool, buildClauses(filters), null);
}

function bucketize(value: number, breakpoints: number[]): number {
  let idx = 0;
  while (idx < breakpoints.length && value >= breakpoints[idx]) idx += 1;
  return idx;
}

function computeBuckets(pool: SearchIndexEntry[], field: "iso" | "focal_length", breakpoints: number[]): FacetBucket[] {
  const counts = new Array(breakpoints.length + 1).fill(0);
  for (const entry of pool) {
    const value = entry[field];
    if (value == null) continue;
    counts[bucketize(value, breakpoints)] += 1;
  }
  return counts.map((count, idx) => ({
    // `from_` : nom de champ réel du contrat (Pydantic `from_`, `from` étant un mot réservé
    // Python — § alias non défini côté backend, donc `from_` traverse tel quel jusqu'au JSON).
    from_: idx === 0 ? null : breakpoints[idx - 1],
    to: idx === breakpoints.length ? null : breakpoints[idx],
    count,
  }));
}

function termFacet(
  pool: SearchIndexEntry[],
  extract: (entry: SearchIndexEntry) => (number | string)[],
  resolveLabel: (value: number | string) => string | null,
): FacetTerm[] {
  const counts = new Map<number | string, number>();
  for (const entry of pool) {
    for (const value of extract(entry)) {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
  }
  const terms: FacetTerm[] = [];
  for (const [value, count] of counts) {
    const label = resolveLabel(value);
    if (label == null) continue;
    terms.push({ id: typeof value === "number" ? value : hashStringId(value), label, count });
  }
  return terms.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "fr"));
}

/** `FacetTerm.id` est `int` dans le contrat — les facettes textuelles (`lens`, `car_number`)
 * n'ont pas d'id numérique naturel : hash déterministe stable, jamais recalculé côté serveur
 * (cette fonction n'existe que côté fixtures, uniquement pour peupler `FacetTerm.id`). */
function hashStringId(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return hash;
}

function statusFacet(pool: SearchIndexEntry[]): FacetStatusTerm[] {
  const counts = new Map<AttachmentStatus, number>();
  for (const entry of pool) counts.set(entry.attachment_status, (counts.get(entry.attachment_status) ?? 0) + 1);
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count);
}

export function computeFacets(pool: SearchIndexEntry[], filters: SearchFilters, labels: LabelResolvers): Facets {
  const clauses = buildClauses(filters);
  const exceptShooting = applyClauses(pool, clauses, "shooting");
  const exceptClient = applyClauses(pool, clauses, "client");
  const exceptTeam = applyClauses(pool, clauses, "team");
  const exceptDriver = applyClauses(pool, clauses, "driver");
  const exceptCarNumber = applyClauses(pool, clauses, "car_number");
  const exceptCircuit = applyClauses(pool, clauses, "circuit");
  const exceptCamera = applyClauses(pool, clauses, "camera");
  const exceptLens = applyClauses(pool, clauses, "lens");
  const exceptStatus = applyClauses(pool, clauses, "status");
  // Mono-sélection (§3-K.2) : jeu filtré complet, filtre inclus.
  const fullyFiltered = applyClauses(pool, clauses, null);

  return {
    shooting: termFacet(exceptShooting, (e) => (e.shooting_id != null ? [e.shooting_id] : []), (v) =>
      labels.shooting(v as number),
    ),
    client: termFacet(exceptClient, (e) => (e.client_id != null ? [e.client_id] : []), (v) => labels.client(v as number)),
    team: termFacet(exceptTeam, (e) => e.team_ids, (v) => labels.team(v as number)),
    driver: termFacet(exceptDriver, (e) => e.driver_ids, (v) => labels.driver(v as number)),
    car_number: termFacet(exceptCarNumber, (e) => e.car_numbers, (v) => String(v)),
    circuit: termFacet(exceptCircuit, (e) => (e.circuit_id != null ? [e.circuit_id] : []), (v) =>
      labels.circuit(v as number),
    ),
    camera: termFacet(exceptCamera, (e) => (e.camera_id != null ? [e.camera_id] : []), (v) => labels.camera(v as number)),
    lens: termFacet(exceptLens, (e) => (e.lens != null ? [e.lens] : []), (v) => String(v)),
    status: statusFacet(exceptStatus),
    iso: computeBuckets(fullyFiltered, "iso", ISO_BREAKPOINTS),
    focal: computeBuckets(fullyFiltered, "focal_length", FOCAL_BREAKPOINTS),
  };
}

function sortKey(entry: SearchIndexEntry, sort: SortMode): string {
  // `shot_at` nul trié en dernier quel que soit le sens — chaîne de remplacement hors bornes
  // ISO 8601 réelles (`0000-00-00` mine, `9999-99-99` maxi) pour rester une comparaison de
  // chaînes simple, cohérente avec `-shot_at`/`shot_at`.
  const value = entry.shot_at ?? (sort === "-shot_at" ? "0000-00-00T00:00:00Z" : "9999-99-99T99:99:99Z");
  return value;
}

function compareEntries(a: SearchIndexEntry, b: SearchIndexEntry, sort: SortMode): number {
  const ka = sortKey(a, sort);
  const kb = sortKey(b, sort);
  if (ka !== kb) {
    return sort === "-shot_at" ? (ka < kb ? 1 : -1) : ka < kb ? -1 : 1;
  }
  // Départage stable par id, même sens que le tri principal (§3-K.2, curseur `(shot_at, id)`).
  return sort === "-shot_at" ? b.id - a.id : a.id - b.id;
}

export function encodeCursor(entry: SearchIndexEntry, sort: SortMode): string {
  const payload = `${sortKey(entry, sort)}|${entry.id}`;
  return typeof window === "undefined" ? Buffer.from(payload).toString("base64") : btoa(payload);
}

function decodeCursor(cursor: string): { key: string; id: number } | null {
  try {
    const raw = typeof window === "undefined" ? Buffer.from(cursor, "base64").toString("utf-8") : atob(cursor);
    const [key, idRaw] = raw.split("|");
    const id = Number.parseInt(idRaw, 10);
    if (!key || Number.isNaN(id)) return null;
    return { key, id };
  } catch {
    return null;
  }
}

export type SearchResult = {
  items: SearchIndexEntry[];
  facets: Facets;
  total: number;
  next_cursor: string | null;
  took_ms: number;
};

export function runSearch(
  pool: SearchIndexEntry[],
  filters: SearchFilters,
  labels: LabelResolvers,
  cursor: string | null | undefined,
  limit: number,
): SearchResult {
  const startedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
  const clauses = buildClauses(filters);
  const filtered = applyClauses(pool, clauses, null);
  const sort = filters.sort ?? "-shot_at";
  const sorted = [...filtered].sort((a, b) => compareEntries(a, b, sort));

  let startIndex = 0;
  const decoded = cursor ? decodeCursor(cursor) : null;
  if (decoded) {
    const idx = sorted.findIndex((e) => sortKey(e, sort) === decoded.key && e.id === decoded.id);
    startIndex = idx >= 0 ? idx + 1 : 0;
  }
  const page = sorted.slice(startIndex, startIndex + limit);
  const nextEntry = sorted[startIndex + limit];
  const facets = computeFacets(pool, filters, labels);
  const finishedAt = typeof performance !== "undefined" ? performance.now() : Date.now();

  return {
    items: page,
    facets,
    total: sorted.length,
    next_cursor: nextEntry ? encodeCursor(page[page.length - 1], sort) : null,
    took_ms: Math.round((finishedAt - startedAt) * 100) / 100,
  };
}
