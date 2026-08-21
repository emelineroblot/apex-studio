import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/review";
import type { MediaOcrResponse, ReviewDecision, ReviewDecisionsResponse, ReviewQueueResponse } from "@/lib/api/types";

export async function queue(
  params: { shooting_id?: number | null; cursor?: string | null; limit?: number } = {},
): Promise<ReviewQueueResponse> {
  const limit = params.limit ?? 25;
  if (API_MODE === "fixtures") {
    return fixtures.queue(params.shooting_id, params.cursor, limit);
  }
  return apiRequest<ReviewQueueResponse>("/review/queue", {
    query: { shooting_id: params.shooting_id, cursor: params.cursor, limit },
  });
}

/** `POST /review/decisions` — transaction unique, erreurs partielles rapportées ligne par
 * ligne (§3-J.4/contrat). Jamais un appel par décision : c'est tout l'intérêt du lot. */
export async function decide(decisions: ReviewDecision[]): Promise<ReviewDecisionsResponse> {
  if (API_MODE === "fixtures") {
    return fixtures.decide(decisions);
  }
  return apiRequest<ReviewDecisionsResponse>("/review/decisions", {
    method: "POST",
    json: { decisions },
  });
}

/** `GET /media/{id}/ocr` — historique des candidats OCR d'un média, décisions incluses. */
export async function ocrCandidates(mediaId: number): Promise<MediaOcrResponse> {
  if (API_MODE === "fixtures") {
    const candidates = await fixtures.candidatesForMedia(mediaId);
    return { candidates };
  }
  return apiRequest<MediaOcrResponse>(`/media/${mediaId}/ocr`);
}
