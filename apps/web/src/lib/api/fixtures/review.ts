/**
 * File de validation OCR (mode "fixtures") — rejoue `apex/pipeline/ocr/classify.py` +
 * `routers/review.py` (§3-J.3/§3-J.4) : les candidats **bruts** (`media_ocr_candidate`)
 * sont la source de vérité, une décision humaine les fait passer à `accepted`/`rejected`
 * sans jamais les supprimer — même invariant que le backend (§3-E.6, idempotence).
 */
import type {
  MediaEngagementOut,
  ReviewDecision,
  ReviewDecisionsResponse,
  ReviewItem,
  ReviewQueueResponse,
  SuggestedEngagement,
} from "@/lib/api/types";
import { clients, drivers, engagements, media, mediaThumbUrl, ocrCandidates, teams } from "@/lib/api/fixtures/db";
import { delay, paginate } from "@/lib/api/fixtures/utils";

const MAX_ALTERNATIVES = 9;

function toSuggested(engagementId: number): SuggestedEngagement | null {
  const engagement = engagements.find((e) => e.id === engagementId);
  if (!engagement) return null;
  return {
    id: engagement.id,
    car_number: engagement.car_number,
    driver: engagement.driver_id != null ? (drivers.find((d) => d.id === engagement.driver_id)?.full_name ?? null) : null,
    team: engagement.team_id != null ? (teams.find((t) => t.id === engagement.team_id)?.name ?? null) : null,
    client: engagement.client_id != null ? (clients.find((c) => c.id === engagement.client_id)?.name ?? null) : null,
  };
}

/** Candidats encore à trancher — non filtrés côté fixtures, contrairement à `list()`, pour
 * être réutilisés par `GET /media/{id}/ocr` (historique complet, décisions incluses). */
function unresolvedCandidates(shootingId: number | null | undefined) {
  return ocrCandidates.filter((c) => {
    if (c.resolution !== "review" && c.resolution !== "not_engaged") return false;
    if (shootingId == null) return true;
    const item = media.find((m) => m.id === c.media_id);
    return item?.shooting_id === shootingId;
  });
}

function toReviewItem(candidateId: number): ReviewItem | null {
  const candidate = ocrCandidates.find((c) => c.id === candidateId);
  if (!candidate) return null;
  const item = media.find((m) => m.id === candidate.media_id);
  if (!item) return null;

  const shootingEngagements = item.shooting_id != null ? engagements.filter((e) => e.shooting_id === item.shooting_id) : [];
  const suggested = candidate.engagement_id != null ? toSuggested(candidate.engagement_id) : null;
  const others = shootingEngagements
    .filter((e) => e.id !== candidate.engagement_id)
    .slice(0, MAX_ALTERNATIVES)
    .map((e) => toSuggested(e.id))
    .filter((e): e is SuggestedEngagement => e != null);

  return {
    candidate_id: candidate.id,
    media: {
      id: item.id,
      thumb_url: mediaThumbUrl(item),
      preview_url: mediaThumbUrl(item),
      shot_at: item.shot_at,
    },
    raw_text: candidate.raw_text,
    normalized_number: candidate.normalized_number,
    confidence: candidate.confidence,
    bbox: candidate.bbox,
    // `resolution` est désormais explicite sur `ReviewItem` (§ passe d'intégration live
    // J2) — la distinction « pas sûr » (`review`) vs « incohérent » (`not_engaged`) ne se
    // déduit plus de la nullabilité de `suggested_engagement`, voir `ReviewCard.tsx`.
    resolution: candidate.resolution,
    suggested_engagement: suggested,
    other_engagements: others,
  };
}

export async function queue(
  shootingId: number | null | undefined,
  cursor: string | null | undefined,
  limit: number,
): Promise<ReviewQueueResponse> {
  await delay(240);
  const candidates = unresolvedCandidates(shootingId).sort((a, b) => a.id - b.id);
  const page = paginate(candidates, cursor, limit);
  const items = page.items.map((c) => toReviewItem(c.id)).filter((i): i is ReviewItem => i != null);
  return { items, remaining: candidates.length, next_cursor: page.next_cursor };
}

/** Fait passer un média `pending_review`/`inconsistent` sans candidat encore en attente vers
 * `shooting_attached` — reflète `attach_time` sans rattachement d'engagement, jamais
 * `unattached` (le média reste dans la fenêtre temporelle du shooting). */
function reconcileMediaStatus(mediaId: number) {
  const item = media.find((m) => m.id === mediaId);
  if (!item) return;
  const stillPending = ocrCandidates.some(
    (c) => c.media_id === mediaId && (c.resolution === "review" || c.resolution === "not_engaged"),
  );
  if (stillPending) return;
  if (item.engagements.length > 0) {
    item.attachment_status = "engagement_attached";
  } else if (item.attachment_status === "pending_review" || item.attachment_status === "inconsistent") {
    item.attachment_status = "shooting_attached";
  }
}

export async function decide(decisions: ReviewDecision[]): Promise<ReviewDecisionsResponse> {
  await delay(300);
  let applied = 0;
  let skipped = 0;
  const errors: ReviewDecisionsResponse["errors"] = [];
  const touchedMediaIds = new Set<number>();

  for (const decision of decisions) {
    const candidate = ocrCandidates.find((c) => c.id === decision.candidate_id);
    if (!candidate) {
      skipped += 1;
      errors.push({ candidate_id: decision.candidate_id, message: "Candidat introuvable ou déjà traité." });
      continue;
    }
    if (candidate.resolution !== "review" && candidate.resolution !== "not_engaged") {
      skipped += 1;
      errors.push({ candidate_id: decision.candidate_id, message: "Ce candidat a déjà été tranché." });
      continue;
    }
    const item = media.find((m) => m.id === candidate.media_id);
    if (!item) {
      skipped += 1;
      errors.push({ candidate_id: decision.candidate_id, message: "Média associé introuvable." });
      continue;
    }

    if (decision.action === "accept") {
      if (candidate.engagement_id == null) {
        skipped += 1;
        errors.push({ candidate_id: decision.candidate_id, message: "Aucun engagement suggéré à accepter — utilisez « rattacher à ».", });
        continue;
      }
      attachEngagement(item.engagements, candidate.engagement_id, "ocr", candidate.confidence);
      // La lecture reste d'origine OCR (l'humain confirme, il ne relit pas) — cohérent avec
      // `fixtures/stats.ts::autoAttachRate`, qui bucket par `attachment_source`.
      item.attachment_source = "pipeline_ocr";
      candidate.resolution = "accepted";
    } else if (decision.action === "reject") {
      candidate.resolution = "rejected";
    } else if (decision.action === "reassign") {
      if (decision.engagement_id == null || !engagements.some((e) => e.id === decision.engagement_id)) {
        skipped += 1;
        errors.push({ candidate_id: decision.candidate_id, message: "Engagement de rattachement invalide." });
        continue;
      }
      attachEngagement(item.engagements, decision.engagement_id, "human", null);
      // Ici l'humain a choisi une correspondance que la machine n'avait pas proposée —
      // rattachement d'origine humaine, pas OCR (§ tâche 5, taux de rattachement auto).
      item.attachment_source = "human";
      candidate.engagement_id = decision.engagement_id;
      candidate.resolution = "accepted";
    }

    applied += 1;
    touchedMediaIds.add(item.id);
  }

  for (const id of touchedMediaIds) reconcileMediaStatus(id);

  const remaining = unresolvedCandidates(null).length;
  return { applied, skipped, errors, remaining };
}

function attachEngagement(
  list: MediaEngagementOut[],
  engagementId: number,
  source: MediaEngagementOut["source"],
  confidence: number | null,
) {
  const existing = list.find((e) => e.engagement_id === engagementId);
  const engagement = engagements.find((e) => e.id === engagementId);
  if (!engagement) return;
  if (existing) {
    existing.source = source;
    existing.confidence = confidence;
    return;
  }
  list.push({ engagement_id: engagementId, car_number: engagement.car_number, source, confidence });
}

/** `GET /media/{id}/ocr` — tous les candidats (tranchés ou non) d'un média, jamais filtrés. */
export async function candidatesForMedia(mediaId: number) {
  await delay(150);
  return ocrCandidates.filter((c) => c.media_id === mediaId);
}
