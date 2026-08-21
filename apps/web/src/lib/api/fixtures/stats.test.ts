import { describe, expect, it } from "vitest";
import { autoAttachRate } from "@/lib/api/fixtures/stats";
import { media } from "@/lib/api/fixtures/db";

/**
 * Contrat final (§ intégration live J2) — `AutoAttachRate.real`/`.simulated` (revue J2 🟠1) :
 * la ligne de tête reste l'agrégat toutes origines confondues, et chaque population isole
 * strictement ses médias (`is_simulated`), sans double-compte ni fuite d'une population dans
 * l'autre — même invariant que celui vérifié côté backend (`test_the_rate_is_ventilated_by_
 * origin_rather_than_blended`, § `implementation.md`).
 */
describe("fixtures/stats — autoAttachRate() ventile réel/simulé sans les mélanger", () => {
  it("real.total + simulated.total == total, et chaque population ne compte que ses médias", async () => {
    const rate = await autoAttachRate({});
    expect(rate.real.total + rate.simulated.total).toBe(rate.total);

    const scoped = media.filter((m) => m.ingest_status === "ingested" && m.duplicate_of_media_id == null);
    const expectedReal = scoped.filter((m) => !m.is_simulated).length;
    const expectedSimulated = scoped.filter((m) => m.is_simulated).length;
    expect(rate.real.total).toBe(expectedReal);
    expect(rate.simulated.total).toBe(expectedSimulated);
  });

  it("le taux d'une population vide reste 0, jamais une division par zéro", async () => {
    const rate = await autoAttachRate({});
    // Jeu de fixtures actuel : pas de média réel (même situation que le jeu de démo tant que
    // `demo-photos/` est absent, § brief) — vérifie que la population vide ne casse rien.
    if (rate.real.total === 0) {
      expect(rate.real.rate).toBe(0);
    }
  });
});
