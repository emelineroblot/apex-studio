/**
 * Logique **pure** partagée par `FacetCheckboxGroup`/`FacetCheckboxGroupText` (revue J2
 * 🟡14) — testable sans DOM ni React, même méthode que `lib/review/batch.ts`.
 *
 * `GET /search` tronque chaque facette à `FACET_TERM_LIMIT` (50) valeurs, par volume. Un
 * filtre **actif** dont la valeur ne fait pas partie de ce top 50 disparaît alors purement
 * et simplement du panneau — il reste appliqué (la requête le porte toujours), mais
 * l'utilisateur ne peut plus le décocher sans réinitialiser tous les filtres, faute d'un
 * contrôle à cliquer. `missingSelectedTerms` calcule les valeurs sélectionnées absentes de
 * la liste renvoyée, pour que le panneau les réinjecte toujours, quelle que soit leur
 * position dans le classement backend.
 */
import type { FacetTerm } from "@/lib/api/types";

export function missingSelectedTerms<Value>(
  terms: readonly FacetTerm[],
  selected: readonly Value[],
  isMatch: (term: FacetTerm, value: Value) => boolean,
  toTerm: (value: Value) => FacetTerm,
): FacetTerm[] {
  return selected.filter((value) => !terms.some((term) => isMatch(term, value))).map(toTerm);
}

/** Id synthétique déterministe pour les facettes textuelles (`car_number`, `lens`) — le
 * contrat impose `FacetTerm.id: int` même pour ces facettes dont la valeur de filtre réelle
 * est la chaîne (`label`), jamais un identifiant numérique métier. Purement local à
 * l'affichage (`inputId`/`key`), jamais transmis à l'API. Même algorithme que
 * `lib/search/engine.ts::hashStringId` (fixtures) — dupliqué à dessein : ce module ne doit
 * dépendre d'aucune logique de moteur de recherche.
 */
export function hashStringId(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return hash;
}
