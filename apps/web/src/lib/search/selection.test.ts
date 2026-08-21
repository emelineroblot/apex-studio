import { describe, expect, it } from "vitest";
import { toggleWithRange } from "@/lib/search/selection";

const ids = [10, 20, 30, 40, 50];

describe("lib/search/selection — sélection multiple avec Shift+clic", () => {
  it("un clic simple bascule uniquement l'élément cliqué", () => {
    const { next, lastIndex } = toggleWithRange(new Set(), ids, 2, null, false);
    expect([...next]).toEqual([30]);
    expect(lastIndex).toBe(2);
  });

  it("Shift+clic sélectionne toute la plage entre le dernier index et l'index cliqué", () => {
    const first = toggleWithRange(new Set(), ids, 1, null, false); // sélectionne #20, lastIndex=1
    const { next } = toggleWithRange(first.next, ids, 3, first.lastIndex, true); // Shift jusqu'à #40
    expect([...next].sort((a, b) => a - b)).toEqual([20, 30, 40]);
  });

  it("Shift+clic fonctionne aussi en remontant (index cliqué avant le dernier index)", () => {
    const first = toggleWithRange(new Set(), ids, 3, null, false); // #40, lastIndex=3
    const { next } = toggleWithRange(first.next, ids, 0, first.lastIndex, true); // Shift jusqu'à #10
    expect([...next].sort((a, b) => a - b)).toEqual([10, 20, 30, 40]);
  });

  it("un second clic simple sur un élément déjà sélectionné le désélectionne", () => {
    const first = toggleWithRange(new Set(), ids, 2, null, false); // sélectionne #30
    const { next } = toggleWithRange(first.next, ids, 2, first.lastIndex, false);
    expect(next.size).toBe(0);
  });

  it("Shift+clic sans sélection préalable (lastIndex nul) se comporte comme un clic simple", () => {
    const { next } = toggleWithRange(new Set(), ids, 2, null, true);
    expect([...next]).toEqual([30]);
  });
});
