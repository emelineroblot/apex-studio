import { describe, expect, it, vi } from "vitest";

// Sans session active (pas de connexion simulée dans cet environnement de test),
// `fixtures/access.ts::visibleShootingIdsForCurrentUser` renvoie `[]` (liste vide, pas
// `null`) — `Boolean([])` est `true` en JS, donc `resources/media.ts::list()` appliquerait
// silencieusement un filtre de visibilité qui exclut tout le jeu de fixtures. On rejoue un
// rôle `owner` (aucune restriction, `null`) : ce test porte sur `series`/`duplicates`, pas
// sur le cloisonnement par rôle (déjà couvert côté backend, `tests/test_access.py`).
vi.mock("@/lib/api/fixtures/access", () => ({
  currentUserId: () => 1,
  visibleShootingIdsForCurrentUser: () => null,
}));

const mediaApi = await import("@/lib/api/resources/media");

/**
 * Contrat régénéré ce lot (`services/api/openapi.json` → `npm run gen:api`) :
 * `MediaSummary.series_id`/`series_member_count`, `GET /media?series=collapsed|all` et
 * `GET /media?duplicates=true`. Vérifie que `resources/media.ts` (mode fixtures, celui
 * utilisé par la démo sans backend) respecte réellement ces deux critères d'acceptation
 * J1 : « une rafale est regroupée en série et n'affiche qu'un représentant » et « deux
 * fichiers identiques sont dédoublonnés » (l'onglet Doublons ne doit jamais rester
 * structurellement vide).
 */
describe("resources/media.ts — collapse des rafales (fixtures)", () => {
  it("series=collapsed (défaut) ne renvoie qu'un représentant par rafale", async () => {
    const collapsed = await mediaApi.list({ limit: 100 });
    const all = await mediaApi.list({ series: "all", limit: 100 });

    const seriesIdsInCollapsed = collapsed.items.map((m) => m.series_id).filter((id): id is number => id != null);
    expect(seriesIdsInCollapsed.length).toBeGreaterThan(0); // le jeu de fixtures contient au moins une rafale

    // Chaque série présente dans la page collapsée n'y apparaît qu'une seule fois.
    const uniqueSeriesIds = new Set(seriesIdsInCollapsed);
    expect(seriesIdsInCollapsed.length).toBe(uniqueSeriesIds.size);

    for (const seriesId of uniqueSeriesIds) {
      const membersInAll = all.items.filter((m) => m.series_id === seriesId);
      const representativeInCollapsed = collapsed.items.find((m) => m.series_id === seriesId);
      expect(representativeInCollapsed, `série #${seriesId} absente de la page collapsée`).toBeDefined();
      // Le représentant porte le compte total de membres de la série — pas 1.
      expect(representativeInCollapsed?.series_member_count).toBe(membersInAll.length);
      expect(membersInAll.length).toBeGreaterThan(1); // sinon ce n'est pas une vraie rafale
    }
  });

  it("series=all renvoie tous les membres d'une rafale, pas seulement le représentant", async () => {
    const collapsed = await mediaApi.list({ limit: 100 });
    const all = await mediaApi.list({ series: "all", limit: 100 });
    // `all` ne peut jamais renvoyer moins d'éléments que `collapsed` pour la même page.
    expect(all.items.length).toBeGreaterThan(collapsed.items.length);
  });

  it("aucun média hors rafale ni doublon n'est affecté par le paramètre series", async () => {
    const collapsed = await mediaApi.list({ limit: 100 });
    const all = await mediaApi.list({ series: "all", limit: 100 });
    const isolatedInCollapsed = collapsed.items.filter((m) => m.series_id == null).map((m) => m.id);
    const isolatedInAll = all.items.filter((m) => m.series_id == null).map((m) => m.id);
    expect(new Set(isolatedInAll)).toEqual(new Set(isolatedInCollapsed));
  });
});

describe("resources/media.ts — onglet Doublons (fixtures)", () => {
  it("par défaut, la liste n'inclut jamais de doublon", async () => {
    const page = await mediaApi.list({ limit: 100 });
    expect(page.items.some((m) => m.duplicate_of_media_id != null)).toBe(false);
  });

  it("duplicates=true ne renvoie que des doublons, jamais vide sur le jeu de fixtures", async () => {
    const page = await mediaApi.list({ duplicates: true, limit: 100 });
    expect(page.items.length).toBeGreaterThan(0); // l'onglet ne doit pas être structurellement vide
    for (const item of page.items) {
      expect(item.duplicate_of_media_id).not.toBeNull();
    }
  });

  it("chaque doublon renvoyé pointe vers un maître consultable via get()", async () => {
    const page = await mediaApi.list({ duplicates: true, limit: 100 });
    for (const item of page.items) {
      const masterId = item.duplicate_of_media_id as number;
      const master = await mediaApi.get(masterId);
      expect(master.id).toBe(masterId);
      expect(master.duplicate_of_media_id).toBeNull(); // le maître n'est pas lui-même un doublon
    }
  });
});
