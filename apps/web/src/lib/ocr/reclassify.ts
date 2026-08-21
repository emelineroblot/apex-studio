/**
 * Reclassement des candidats OCR par seuil — logique **pure**, sans I/O (`reclassify.test.ts`),
 * partagée par `fixtures/settings.ts` (mode démo) et par tout composant qui doit prévisualiser
 * une redistribution. Rejoue exactement la règle décrite §3-J.3/§3-J.4 du plan :
 *
 * - un candidat **sans engagement trouvé** (numéro absent de la table des engagements) reste
 *   `not_engaged` **quel que soit le score** — le seuil ne fait jamais entrer un numéro
 *   incohérent en rattachement automatique (critère d'acceptation « jamais rattaché de
 *   force ») ;
 * - un candidat déjà tranché par un humain (`accepted`/`rejected`) n'est **jamais** rejoué —
 *   § « les décisions humaines déjà prises sont préservées » ;
 * - sinon, le score seul décide : `≥ high` → `auto`, `[low, high[` → `review`, `< low` →
 *   `abstain`.
 *
 * Ce module ne relit jamais une image ni n'appelle de moteur OCR — c'est tout l'intérêt du
 * point de design §3-J.4 : « changer les seuils redistribue les cas, sans relancer
 * l'inférence ».
 */
import type { OcrCandidateOut, OcrDistribution, OcrPreviewDistribution } from "@/lib/api/types";

export type OcrThresholds = { high: number; low: number };

type Reclassifiable = Pick<OcrCandidateOut, "confidence" | "engagement_id" | "resolution">;

export function reclassifyResolution(
  candidate: Reclassifiable,
  thresholds: OcrThresholds,
): OcrCandidateOut["resolution"] {
  if (candidate.resolution === "accepted" || candidate.resolution === "rejected") return candidate.resolution;
  if (candidate.engagement_id == null) return "not_engaged";
  if (candidate.confidence >= thresholds.high) return "auto";
  if (candidate.confidence >= thresholds.low) return "review";
  return "abstain";
}

/** Distribution complète (4 cases) parmi les candidats **non tranchés par un humain** — les
 * `accepted`/`rejected` sont des états terminaux, hors de ce classement à seuils. */
export function computeDistribution(candidates: readonly Reclassifiable[], thresholds: OcrThresholds): OcrDistribution {
  const distribution: OcrDistribution = { auto: 0, review: 0, abstain: 0, not_engaged: 0 };
  for (const candidate of candidates) {
    const resolution = reclassifyResolution(candidate, thresholds);
    if (resolution === "auto" || resolution === "review" || resolution === "abstain" || resolution === "not_engaged") {
      distribution[resolution] += 1;
    }
  }
  return distribution;
}

/** `OcrSettingsUpdateResponse.preview_distribution` — mêmes trois premières cases, sans
 * `not_engaged` (le schéma du contrat l'exclut : ce bac ne bouge jamais avec les seuils, le
 * montrer dans un aperçu « ce qui va changer » serait trompeur). */
export function computePreviewDistribution(
  candidates: readonly Reclassifiable[],
  thresholds: OcrThresholds,
): OcrPreviewDistribution {
  const { auto, review, abstain } = computeDistribution(candidates, thresholds);
  return { auto, review, abstain };
}
