import { describe, expect, it } from "vitest";
import { decide, queue } from "@/lib/api/fixtures/review";
import { media } from "@/lib/api/fixtures/db";

/**
 * Revue J2 🟠7 — `POST /review/decisions` doit renvoyer un `remaining` scopé à la même
 * population que `GET /review/queue`, sinon la barre de progression de `review/page.tsx`
 * compare deux univers différents dès qu'un filtre de shooting est actif (§ scénario de la
 * revue : 384 candidats au total, 20 sur le shooting filtré → barre vide, « 379 restants »
 * affichés sur une file qui en contient réellement 15). Reproduit ici avec les mêmes
 * proportions que le jeu de fixtures, jamais des ids codés en dur — pour rester correct si
 * le jeu de démo évolue.
 */
describe("fixtures/review — decide() scope 'remaining' comme queue() (revue J2 🟠7)", () => {
  it("le remaining après décision reste dans la population du shooting filtré, pas le total global", async () => {
    const globalBefore = await queue(null, null, 100);
    const first = globalBefore.items[0];
    expect(first).toBeDefined();

    const item = media.find((m) => m.id === first.media.id);
    expect(item?.shooting_id).not.toBeNull();
    const shootingId = item!.shooting_id as number;

    const scopedBefore = await queue(shootingId, null, 100);
    // Le test n'a de sens que si le shooting filtré est un sous-ensemble strict du total —
    // sinon la scoping ne changerait jamais rien et le test ne prouverait rien.
    expect(scopedBefore.remaining).toBeLessThan(globalBefore.remaining);

    const res = await decide([{ candidate_id: first.candidate_id, action: "reject" }], shootingId);

    expect(res.remaining).toBe(scopedBefore.remaining - 1);
    // Preuve négative : l'ancien comportement (remaining global) aurait renvoyé
    // `globalBefore.remaining - 1`, une valeur différente ici — s'assurer que la correction
    // ne renvoie pas silencieusement à ce calcul-là.
    expect(res.remaining).not.toBe(globalBefore.remaining - 1);
  });

  it("sans shootingId (file « Tous »), remaining reste le total global — comportement inchangé", async () => {
    const before = await queue(null, null, 100);
    const first = before.items[0];
    const res = await decide([{ candidate_id: first.candidate_id, action: "reject" }], null);
    expect(res.remaining).toBe(before.remaining - 1);
  });
});
