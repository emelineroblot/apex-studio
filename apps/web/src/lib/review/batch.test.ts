import { describe, expect, it } from "vitest";
import {
  clampIndex,
  computeQueueProgress,
  nextUndecidedIndex,
  resolveBatchTargets,
  stageDecisions,
  toReviewDecisionsPayload,
  toggleSelection,
  unstageDecision,
} from "@/lib/review/batch";

describe("lib/review/batch — ciblage d'une action clavier", () => {
  it("cible uniquement l'élément focalisé quand aucune sélection en lot n'est active", () => {
    expect(resolveBatchTargets(new Set(), 42)).toEqual([42]);
  });

  it("cible toute la sélection en lot quand elle est non vide, même si l'élément focalisé n'y est pas", () => {
    const selected = new Set([1, 2, 3]);
    expect(resolveBatchTargets(selected, 99).sort()).toEqual([1, 2, 3]);
  });

  it("aucune cible si ni sélection ni élément focalisé", () => {
    expect(resolveBatchTargets(new Set(), null)).toEqual([]);
  });
});

describe("lib/review/batch — empilement des décisions", () => {
  it("stageDecisions applique la même action à toute une sélection en une fois", () => {
    const decisions = stageDecisions(new Map(), [1, 2, 3], "accept");
    expect(decisions.size).toBe(3);
    expect(decisions.get(2)).toEqual({ candidateId: 2, action: "accept", engagementId: null });
  });

  it("une décision réécrit la précédente pour le même candidat (dernier appel gagnant)", () => {
    let decisions = stageDecisions(new Map(), [1], "accept");
    decisions = stageDecisions(decisions, [1], "reject");
    expect(decisions.get(1)?.action).toBe("reject");
  });

  it("un candidat ne porte jamais deux décisions à la fois, même en lot puis individuel", () => {
    let decisions = stageDecisions(new Map(), [1, 2, 3], "reject");
    decisions = stageDecisions(decisions, [2], "accept");
    expect(decisions.get(1)?.action).toBe("reject");
    expect(decisions.get(2)?.action).toBe("accept");
    expect(decisions.get(3)?.action).toBe("reject");
    expect(decisions.size).toBe(3);
  });

  it("reassign porte l'engagement_id, accept/reject ne le portent jamais", () => {
    const decisions = stageDecisions(new Map(), [1], "reassign", 55);
    expect(decisions.get(1)).toEqual({ candidateId: 1, action: "reassign", engagementId: 55 });
    const accepted = stageDecisions(new Map(), [1], "accept", 55);
    expect(accepted.get(1)?.engagementId).toBeNull(); // ignoré hors reassign, même si fourni par erreur
  });

  it("unstageDecision retire un candidat précis sans toucher aux autres (« retour arrière »)", () => {
    const decisions = stageDecisions(new Map(), [1, 2], "accept");
    const next = unstageDecision(decisions, 1);
    expect(next.has(1)).toBe(false);
    expect(next.has(2)).toBe(true);
  });
});

describe("lib/review/batch — sélection en lot (Espace)", () => {
  it("toggleSelection ajoute puis retire un candidat", () => {
    let selected = toggleSelection(new Set(), 7);
    expect([...selected]).toEqual([7]);
    selected = toggleSelection(selected, 7);
    expect(selected.size).toBe(0);
  });
});

describe("lib/review/batch — payload POST /review/decisions", () => {
  it("produit un tableau conforme au contrat, ordre d'insertion stable", () => {
    let decisions = stageDecisions(new Map(), [3], "reject");
    decisions = stageDecisions(decisions, [1], "accept");
    decisions = stageDecisions(decisions, [2], "reassign", 9);
    const payload = toReviewDecisionsPayload(decisions);
    expect(payload).toEqual([
      { candidate_id: 3, action: "reject", engagement_id: undefined },
      { candidate_id: 1, action: "accept", engagement_id: undefined },
      { candidate_id: 2, action: "reassign", engagement_id: 9 },
    ]);
  });
});

describe("lib/review/batch — navigation clavier", () => {
  const ids = [10, 20, 30, 40];

  it("nextUndecidedIndex saute les candidats déjà décidés", () => {
    const decisions = stageDecisions(new Map(), [20], "accept"); // index 1 décidé
    const next = nextUndecidedIndex(ids, decisions, 0, 1);
    expect(next).toBe(2); // saute l'index 1, s'arrête sur l'index 2 (id 30)
  });

  it("nextUndecidedIndex boucle en fin de page", () => {
    const next = nextUndecidedIndex(ids, new Map(), 3, 1);
    expect(next).toBe(0);
  });

  it("nextUndecidedIndex reste borné quand tout est décidé", () => {
    const decisions = stageDecisions(new Map(), ids, "accept");
    const next = nextUndecidedIndex(ids, decisions, 1, 1);
    expect(next).toBeGreaterThanOrEqual(0);
    expect(next).toBeLessThan(ids.length);
  });

  it("clampIndex borne dans [0, length-1]", () => {
    expect(clampIndex(-1, 4)).toBe(0);
    expect(clampIndex(10, 4)).toBe(3);
    expect(clampIndex(2, 4)).toBe(2);
    expect(clampIndex(2, 0)).toBe(0);
  });
});

describe("lib/review/batch — computeQueueProgress (revue J2 🟠7)", () => {
  it("calcule la fraction traitée quand numérateur et dénominateur partagent la même population", () => {
    // Scénario exact de la revue : 20 candidats sur le shooting filtré au départ, 15 restants
    // après envoi d'un lot — la barre doit avancer d'un quart, pas rester vide.
    expect(computeQueueProgress(20, 15)).toBeCloseTo(0.25);
  });

  it("reproduit le bug de la revue si on lui passe malgré tout un `remaining` d'une autre population", () => {
    // Avant correction : `initialRemaining` scopé au shooting (20) mais `remainingTotal`
    // renvoyé global (379 sur 384 au total) — la fraction part dans le négatif. La fonction
    // elle-même ne peut pas détecter ce décalage de population (ce n'est pas son rôle : la
    // correction est côté plomberie, § `resources/review.ts::decide`), mais elle doit au
    // moins ne jamais afficher une barre qui déborde de [0, 1] dans ce cas.
    const buggy = computeQueueProgress(20, 379);
    expect(buggy).toBe(0); // bornée à 0, jamais négative malgré le décalage de population
  });

  it("vaut 1 (file terminée) quand le dénominateur de départ est nul ou négatif", () => {
    expect(computeQueueProgress(0, 0)).toBe(1);
  });

  it("reste bornée à 0 (jamais négative) si le restant dépasse le total de départ (nouveaux candidats apparus en session)", () => {
    expect(computeQueueProgress(10, 12)).toBe(0);
  });

  it("vaut 0 en tout début de file (rien encore traité)", () => {
    expect(computeQueueProgress(384, 384)).toBe(0);
  });

  it("vaut 1 quand la file filtrée est intégralement vidée", () => {
    expect(computeQueueProgress(20, 0)).toBe(1);
  });
});
