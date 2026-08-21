/**
 * Logique **pure** de la file de validation OCR (§ tâche 1 du brief J2 — « traiter en lot et
 * au clavier des dizaines de cas ambigus en quelques secondes chacun »). Extraite de
 * `app/(app)/review/page.tsx` pour être testable sans DOM ni React (`batch.test.ts`).
 *
 * Règle de ciblage : si une **sélection multiple** est active (`Espace`), une action
 * (`A`/`R`) s'applique à toute la sélection ; sinon elle ne s'applique qu'à l'élément
 * **focalisé**. Le rattachement à un autre engagement (`1`-`9`) reste, lui, toujours
 * individuel — les suggestions alternatives (`other_engagements`) diffèrent d'une photo à
 * l'autre, les appliquer en lot à une sélection hétérogène rattacherait des photos au
 * mauvais numéro. Décision documentée dans `implementation.md` (le plan liste les touches
 * sans trancher ce point).
 */
import type { ReviewAction, ReviewDecision } from "@/lib/api/types";

export type StagedDecision = {
  candidateId: number;
  action: ReviewAction;
  engagementId: number | null;
};

export type DecisionMap = ReadonlyMap<number, StagedDecision>;

/** Détermine les candidats visés par une action clavier : la sélection en lot si elle est
 * non vide, sinon l'élément focalisé seul. */
export function resolveBatchTargets(selectedIds: ReadonlySet<number>, focusedId: number | null): number[] {
  if (selectedIds.size > 0) return [...selectedIds];
  return focusedId != null ? [focusedId] : [];
}

/** Empile (ou réécrit) une décision pour chaque candidat visé — dernier appel gagnant, un
 * candidat ne porte jamais deux décisions à la fois. */
export function stageDecisions(
  decisions: DecisionMap,
  targetIds: readonly number[],
  action: ReviewAction,
  engagementId: number | null = null,
): Map<number, StagedDecision> {
  const next = new Map(decisions);
  for (const id of targetIds) {
    next.set(id, { candidateId: id, action, engagementId: action === "reassign" ? engagementId : null });
  }
  return next;
}

/** Annule la décision d'un candidat (« retour arrière » sur une correction). */
export function unstageDecision(decisions: DecisionMap, candidateId: number): Map<number, StagedDecision> {
  const next = new Map(decisions);
  next.delete(candidateId);
  return next;
}

/** Bascule la présence d'un candidat dans la sélection en lot (`Espace`). */
export function toggleSelection(selectedIds: ReadonlySet<number>, candidateId: number): Set<number> {
  const next = new Set(selectedIds);
  if (next.has(candidateId)) next.delete(candidateId);
  else next.add(candidateId);
  return next;
}

/** Corps de `POST /review/decisions` — ordre stable (insertion), pour un payload
 * déterministe et testable. */
export function toReviewDecisionsPayload(decisions: DecisionMap): ReviewDecision[] {
  return [...decisions.values()].map((d) => ({
    candidate_id: d.candidateId,
    action: d.action,
    engagement_id: d.action === "reassign" ? (d.engagementId ?? undefined) : undefined,
  }));
}

/** Prochain index **non décidé** à partir de `fromIndex`, dans le sens `direction` (`1` ou
 * `-1`) — utilisé pour l'avance automatique de focus après une décision au clavier, et par
 * `←`/`→`. Reste sur place si tout est décidé (fin de page). */
export function nextUndecidedIndex(
  candidateIds: readonly number[],
  decisions: DecisionMap,
  fromIndex: number,
  direction: 1 | -1,
): number {
  if (candidateIds.length === 0) return fromIndex;
  let idx = fromIndex;
  for (let step = 0; step < candidateIds.length; step += 1) {
    idx += direction;
    if (idx < 0) idx = candidateIds.length - 1;
    if (idx >= candidateIds.length) idx = 0;
    const candidateId = candidateIds[idx];
    if (!decisions.has(candidateId)) return idx;
  }
  // Tout est décidé : reste borné dans la page plutôt que de sortir du tableau.
  return Math.min(Math.max(fromIndex + direction, 0), candidateIds.length - 1);
}

/** Simple navigation bornée (`←`/`→` sans saut de décidés), utilisée en secours quand
 * l'utilisateur veut relire un élément déjà décidé plutôt que d'avancer. */
export function clampIndex(index: number, length: number): number {
  if (length === 0) return 0;
  return Math.min(Math.max(index, 0), length - 1);
}

/**
 * Fraction de la barre de progression de la file de validation (revue J2 🟠7).
 *
 * **La formule elle-même n'a jamais été le bug** : `1 - remaining / initial` est correcte
 * dès lors que les deux nombres décrivent la **même population**. Le bug constaté en revue
 * venait de la plomberie, pas du calcul — `initialRemaining` posé par `GET /review/queue`
 * (scopé sur `shooting_id` si un filtre est actif) tandis que `remainingTotal` revenait de
 * `POST /review/decisions`, qui ignorait ce filtre et renvoyait un total **global**. Avec
 * 384 candidats au total et 20 sur le shooting filtré, la barre affichait `1 − 379/20`
 * (négatif, borné à 0 par `ProgressBar`) au lieu de `1 − 15/20`. Corrigé côté appel en
 * passant désormais `shooting_id` à `POST /review/decisions` (§ `resources/review.ts`) —
 * cette fonction reste néanmoins le bon endroit pour verrouiller la formule par un test,
 * puisqu'une relecture ne l'aurait pas forcément attrapée non plus (les deux nombres
 * *semblent* du même ordre de grandeur tant qu'on ne connaît pas le filtre actif).
 *
 * Bornée à `[0, 1]` — un `remainingTotal` transitoirement supérieur à `initialRemaining`
 * (nouveaux candidats apparus pendant la session) ne doit jamais produire une barre qui
 * recule sous zéro en apparence.
 */
export function computeQueueProgress(initialRemaining: number, remainingTotal: number): number {
  if (initialRemaining <= 0) return 1;
  return Math.min(1, Math.max(0, 1 - remainingTotal / initialRemaining));
}
