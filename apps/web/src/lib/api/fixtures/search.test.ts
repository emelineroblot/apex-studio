import { describe, expect, it } from "vitest";
import { search } from "@/lib/api/fixtures/search";

/**
 * Pagination réelle du mode fixtures (§ pièges projet : « au J1, le bouton "charger plus"
 * n'était pas câblé »). Vérifie que `next_cursor` permet de reconstituer l'intégralité du
 * jeu sans doublon ni omission — pas seulement que la première page a la bonne taille.
 */
describe("fixtures/search — pagination « charger plus »", () => {
  it("accumule toutes les pages jusqu'à next_cursor=null, sans doublon", async () => {
    const seenIds = new Set<number>();
    let cursor: string | null | undefined = null;
    let pages = 0;
    let total = -1;

    do {
      const response = await search({}, cursor, 60);
      if (total === -1) total = response.total;
      expect(response.total).toBe(total); // stable d'une page à l'autre pour les mêmes filtres
      for (const item of response.items) {
        expect(seenIds.has(item.id)).toBe(false); // jamais deux fois le même média
        seenIds.add(item.id);
      }
      cursor = response.next_cursor;
      pages += 1;
    } while (cursor);

    expect(seenIds.size).toBe(total);
    expect(pages).toBeGreaterThan(1); // le jeu de démo dépasse une seule page à limit=60
  });

  it("took_ms est présent et exploitable (critère d'acceptation « temps mesuré et documenté »)", async () => {
    const response = await search({}, null, 20);
    expect(response.took_ms).toBeGreaterThanOrEqual(0);
    expect(response.facets.status.length).toBeGreaterThan(0);
  });
});
