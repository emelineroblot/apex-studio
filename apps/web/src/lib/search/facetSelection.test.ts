import { describe, expect, it } from "vitest";
import { hashStringId, missingSelectedTerms } from "@/lib/search/facetSelection";

describe("lib/search/facetSelection — réinjection d'un filtre coché hors du top 50 (revue J2 🟡14)", () => {
  const terms = [
    { id: 1, label: "Écurie A", count: 40 },
    { id: 2, label: "Écurie B", count: 12 },
  ];

  it("ne réinjecte rien quand toutes les valeurs sélectionnées sont déjà dans `terms`", () => {
    const missing = missingSelectedTerms(terms, [1, 2], (t, id) => t.id === id, (id) => ({
      id,
      label: `#${id}`,
      count: 0,
    }));
    expect(missing).toEqual([]);
  });

  it("réinjecte une valeur sélectionnée absente de `terms` (hors du top 50 backend)", () => {
    // Filtre actif sur l'écurie 99, tronquée par `FACET_TERM_LIMIT` côté backend — sans
    // cette fonction, elle disparaîtrait purement et simplement du panneau.
    const missing = missingSelectedTerms(terms, [1, 99], (t, id) => t.id === id, (id) => ({
      id,
      label: `Filtre actif (#${id})`,
      count: 0,
    }));
    expect(missing).toEqual([{ id: 99, label: "Filtre actif (#99)", count: 0 }]);
  });

  it("réinjecte plusieurs valeurs manquantes, dans l'ordre de la sélection", () => {
    const missing = missingSelectedTerms(terms, [42, 1, 7], (t, id) => t.id === id, (id) => ({
      id,
      label: `#${id}`,
      count: 0,
    }));
    expect(missing.map((t) => t.id)).toEqual([42, 7]);
  });

  it("fonctionne aussi par correspondance de libellé (facettes textuelles car_number/lens)", () => {
    const textTerms = [{ id: 111, label: "RF 70-200mm", count: 20 }];
    const missing = missingSelectedTerms(
      textTerms,
      ["RF 70-200mm", "Sigma 100-400mm"],
      (t, label) => t.label === label,
      (label) => ({ id: hashStringId(label), label, count: 0 }),
    );
    expect(missing).toEqual([{ id: hashStringId("Sigma 100-400mm"), label: "Sigma 100-400mm", count: 0 }]);
  });
});

describe("lib/search/facetSelection — hashStringId", () => {
  it("est déterministe pour une même valeur", () => {
    expect(hashStringId("RF 70-200mm")).toBe(hashStringId("RF 70-200mm"));
  });

  it("distingue deux valeurs différentes (dans la quasi-totalité des cas pratiques)", () => {
    expect(hashStringId("12")).not.toBe(hashStringId("27"));
  });
});
