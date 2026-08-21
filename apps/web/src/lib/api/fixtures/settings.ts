import type { OcrSettingsOut, OcrSettingsUpdate, OcrSettingsUpdateResponse } from "@/lib/api/types";
import { ocrCandidates, ocrSettings } from "@/lib/api/fixtures/db";
import { computeDistribution } from "@/lib/ocr/reclassify";
import { delay, nextId } from "@/lib/api/fixtures/utils";

export async function getOcr(): Promise<OcrSettingsOut> {
  await delay(150);
  return { ...ocrSettings, distribution: computeDistribution(ocrCandidates, ocrSettings) };
}

/**
 * `PUT /settings/ocr` — en mode live, le backend écrit les seuils puis **enqueue**
 * `reclassify_ocr` (asynchrone, § contrat `reclassify_job_id`). En fixtures, sans file à
 * simuler, la re-projection est appliquée en synchrone via `reclassifyResolution` — mêmes
 * candidats bruts, aucun appel au moteur OCR (§3-J.4).
 */
export async function updateOcr(payload: OcrSettingsUpdate): Promise<OcrSettingsUpdateResponse> {
  await delay(220);
  ocrSettings.high = payload.high;
  ocrSettings.low = payload.low;
  if (payload.min_box_area_ratio != null) ocrSettings.min_box_area_ratio = payload.min_box_area_ratio;
  if (payload.max_box_area_ratio != null) ocrSettings.max_box_area_ratio = payload.max_box_area_ratio;
  ocrSettings.updated_at = new Date().toISOString();

  for (const candidate of ocrCandidates) {
    if (candidate.resolution === "accepted" || candidate.resolution === "rejected") continue;
    candidate.resolution =
      candidate.engagement_id == null
        ? "not_engaged"
        : candidate.confidence >= ocrSettings.high
          ? "auto"
          : candidate.confidence >= ocrSettings.low
            ? "review"
            : "abstain";
  }
  const distribution = computeDistribution(ocrCandidates, ocrSettings);
  ocrSettings.distribution = distribution;

  return {
    settings: { ...ocrSettings },
    reclassify_job_id: nextId(),
    preview_distribution: { auto: distribution.auto, review: distribution.review, abstain: distribution.abstain },
  };
}
