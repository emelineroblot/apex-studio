import { beforeEach, describe, expect, it } from "vitest";
import {
  FIXTURE_TOKEN,
  deselectMedia,
  getCollection,
  getSelection,
  openSession,
  resetFixtureState,
  selectMedia,
  validateSelection,
} from "@/lib/api/fixtures/publicSpace";
import { ApiError } from "@/lib/api/errors";

/**
 * Le mode fixtures doit rejouer les règles que l'écran affiche, sinon il donne une
 * confiance fausse : ici, une sélection qui se **fige** à la validation. Un mode fixtures
 * permissif laisserait passer une interface qui propose encore de décocher après coup —
 * exactement ce que le backend refuse par un `409`.
 */
describe("fixtures/publicSpace — l'espace client rejoue les règles du backend", () => {
  beforeEach(() => {
    resetFixtureState();
  });

  it("refuse un jeton inconnu et signale un lien expiré", async () => {
    await expect(openSession("jeton-inconnu")).rejects.toBeInstanceOf(ApiError);
    await expect(openSession("expire")).rejects.toMatchObject({ status: 410 });
    await expect(openSession(FIXTURE_TOKEN)).resolves.toMatchObject({ expires_in: 1800 });
  });

  it("nettoie les commentaires et n'empile pas les doublons", async () => {
    const item = (await getCollection()).items[0];
    await selectMedia(item.media_id, "   ");
    await selectMedia(item.media_id, "  la meilleure  ");

    const selection = await getSelection();
    expect(selection.count).toBe(1);
    expect(selection.items[0].comment).toBe("la meilleure");
  });

  it("fige la sélection une fois validée", async () => {
    const items = (await getCollection()).items;
    await selectMedia(items[0].media_id, null);
    await validateSelection();

    await expect(selectMedia(items[1].media_id, null)).rejects.toMatchObject({ status: 409 });
    await expect(deselectMedia(items[0].media_id)).rejects.toMatchObject({ status: 409 });
    expect((await getSelection()).status).toBe("validated");
  });

  it("refuse de valider une sélection vide", async () => {
    await expect(validateSelection()).rejects.toMatchObject({ status: 409 });
  });

  it("filtre la galerie sur la sélection", async () => {
    const items = (await getCollection()).items;
    await selectMedia(items[2].media_id, null);

    const filtered = await getCollection({ selected_only: true });
    expect(filtered.items.map((item) => item.media_id)).toEqual([items[2].media_id]);
    expect(filtered.items[0].selected).toBe(true);
  });
});
