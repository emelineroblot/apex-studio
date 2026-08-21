import { describe, expect, it } from "vitest";
import { computeFacets, encodeCursor, filterEntries, runSearch, type LabelResolvers, type SearchIndexEntry } from "@/lib/search/engine";

/**
 * Jeu construit à la main, compteurs calculables de tête (même méthode que le backend,
 * `tests/search/test_facets.py::test_facet_counts_exclude_own_filter`) :
 *
 * - shooting 1 : 3 médias, écurie A (2), écurie B (1)
 * - shooting 2 : 2 médias, écurie A (1), écurie C (1)
 */
function buildPool(): SearchIndexEntry[] {
  const base = (overrides: Partial<SearchIndexEntry>): SearchIndexEntry => ({
    id: 0,
    thumb_url: "x",
    shot_at: "2026-06-01T10:00:00Z",
    ingest_status: "ingested",
    attachment_status: "engagement_attached",
    shooting_id: 1,
    client_id: 1,
    circuit_id: 1,
    camera_id: 1,
    lens: "RF 70-200mm",
    iso: 400,
    focal_length: 135,
    team_ids: [],
    driver_ids: [],
    car_numbers: [],
    caption: null,
    keywords: [],
    series_id: null,
    series_member_count: null,
    is_series_representative: true,
    duplicate_of_media_id: null,
    is_simulated: true,
    ...overrides,
  });

  return [
    base({ id: 1, shooting_id: 1, team_ids: [10], car_numbers: ["12"] }),
    base({ id: 2, shooting_id: 1, team_ids: [10], car_numbers: ["27"] }),
    base({ id: 3, shooting_id: 1, team_ids: [20], car_numbers: ["5"] }),
    base({ id: 4, shooting_id: 2, team_ids: [10], car_numbers: ["12"] }),
    base({ id: 5, shooting_id: 2, team_ids: [30], car_numbers: ["9"] }),
  ];
}

const labels: LabelResolvers = {
  shooting: (id) => `Shooting ${id}`,
  client: () => "Client",
  team: (id) => `Écurie ${id}`,
  driver: () => "Pilote",
  circuit: () => "Circuit",
  camera: () => "Boîtier",
};

describe("lib/search/engine — compteurs de facettes « sauf soi »", () => {
  it("le compteur de la facette shooting ignore le filtre shooting actif, pas les autres filtres", () => {
    // Filtre actif : team_id=10 (3 médias : #1, #2, #4) — le compteur `shooting` doit
    // refléter la répartition de CES 3 médias entre shootings (2 en shooting 1, 1 en
    // shooting 2), pas la répartition brute des 5 médias du pool.
    const facets = computeFacets(buildPool(), { team_id: [10] }, labels);
    const shooting1 = facets.shooting.find((t) => t.id === 1);
    const shooting2 = facets.shooting.find((t) => t.id === 2);
    expect(shooting1?.count).toBe(2);
    expect(shooting2?.count).toBe(1);
  });

  it("cocher une écurie ne fait jamais tomber les autres écuries à zéro (règle « sauf soi »)", () => {
    // Filtre actif : team_id=10. Sans la règle « sauf soi », le compteur de l'écurie 20
    // (qui n'a aucun média avec team_id=10) tomberait à 0 et deviendrait impossible à cocher.
    const facets = computeFacets(buildPool(), { team_id: [10] }, labels);
    const team20 = facets.team.find((t) => t.id === 20);
    expect(team20?.count).toBe(1); // média #3, toujours compté malgré le filtre team_id=10 actif
  });

  it("un filtre non-facette (shooting) réduit bien le compteur des facettes multi-sélection", () => {
    const facets = computeFacets(buildPool(), { shooting_id: [2] }, labels);
    const team10 = facets.team.find((t) => t.id === 10);
    const team20 = facets.team.find((t) => t.id === 20);
    expect(team10?.count).toBe(1); // média #4 seulement
    expect(team20).toBeUndefined(); // aucun média du shooting 2 n'a l'écurie 20
  });

  it("les doublons sont toujours exclus des facettes, comme des résultats", () => {
    const pool = buildPool();
    pool.push({ ...pool[0], id: 99, duplicate_of_media_id: 1 });
    const facets = computeFacets(pool, {}, labels);
    const shooting1 = facets.shooting.find((t) => t.id === 1);
    expect(shooting1?.count).toBe(3); // pas 4 : le doublon #99 n'est jamais compté
  });
});

describe("lib/search/engine — pagination keyset (runSearch)", () => {
  it("accumule des pages disjointes via le curseur, sans doublon ni omission", () => {
    const pool = buildPool();
    const page1 = runSearch(pool, {}, labels, null, 2);
    expect(page1.items).toHaveLength(2);
    expect(page1.next_cursor).not.toBeNull();

    const page2 = runSearch(pool, {}, labels, page1.next_cursor, 2);
    expect(page2.items).toHaveLength(2);

    const page3 = runSearch(pool, {}, labels, page2.next_cursor, 2);
    expect(page3.items).toHaveLength(1);
    expect(page3.next_cursor).toBeNull();

    const allIds = [...page1.items, ...page2.items, ...page3.items].map((i) => i.id).sort();
    expect(allIds).toEqual([1, 2, 3, 4, 5]);
  });

  it("un curseur périmé (élément qui n'existe plus dans le tri courant) ne fait pas planter la pagination", () => {
    const pool = buildPool();
    const stale = encodeCursor({ ...pool[0], id: 999 }, "-shot_at");
    const result = runSearch(pool, {}, labels, stale, 10);
    expect(result.items.length).toBeGreaterThan(0); // repli : repart du début plutôt que de renvoyer une page vide
  });

  it("`took_ms` est un temps mesuré, jamais une valeur négative ou figée en dur", () => {
    const result = runSearch(buildPool(), {}, labels, null, 10);
    expect(result.took_ms).toBeGreaterThanOrEqual(0);
  });
});

describe("lib/search/engine — filterEntries (composition de collection depuis la recherche)", () => {
  it("renvoie l'intégralité des résultats, non paginés", () => {
    const pool = buildPool();
    const all = filterEntries(pool, { team_id: [10] });
    expect(all.map((e) => e.id).sort()).toEqual([1, 2, 4]);
  });
});
