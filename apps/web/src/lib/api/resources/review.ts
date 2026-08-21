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

/**
 * `POST /review/decisions` — transaction unique, erreurs partielles rapportées ligne par
 * ligne (§3-J.4/contrat). Jamais un appel par décision : c'est tout l'intérêt du lot.
 *
 * `shootingId` (revue J2 🟠7) : la file de validation accepte un filtre de shooting
 * (`GET /review/queue?shooting_id=…`), mais `remaining` revenait jusqu'ici toujours global —
 * la barre de progression comparait deux populations différentes dès qu'un filtre était
 * actif. Passé en paramètre de requête (comme sur `queue()` ci-dessus), jamais dans le
 * corps : ce n'est pas une donnée de la décision elle-même, c'est le contexte d'où elle est
 * envoyée. § `lib/review/batch.ts::computeQueueProgress` pour la formule côté écran.
 */
export async function decide(
  decisions: ReviewDecision[],
  shootingId?: number | null,
): Promise<ReviewDecisionsResponse> {
  if (API_MODE === "fixtures") {
    return fixtures.decide(decisions, shootingId);
  }
  return apiRequest<ReviewDecisionsResponse>("/review/decisions", {
    method: "POST",
    query: { shooting_id: shootingId },
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
