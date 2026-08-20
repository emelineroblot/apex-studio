import { API_MODE } from "@/lib/env";
import { apiFetchBlob, apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/media";
import { visibleShootingIdsForCurrentUser } from "@/lib/api/fixtures/access";
import type { IngestStatus, MediaOut, MediaSummary, MediaVariant, Page } from "@/lib/api/types";

export type MediaListParams = {
  shooting_id?: number | null;
  status?: IngestStatus | null;
  batch_id?: number | null;
  unattached?: boolean;
  quarantined?: boolean;
  cursor?: string | null;
  limit?: number;
  /** Pas dans le contrat (`GET /media` n'a pas de paramètre dédié aux doublons) : filtre
   * appliqué côté client sur la page courante uniquement, en fixtures comme en live. */
  duplicatesOnly?: boolean;
};

export async function list(params: MediaListParams = {}): Promise<Page<MediaSummary>> {
  if (API_MODE === "fixtures") {
    return fixtures.list(
      { ...params, visibleShootingIds: visibleShootingIdsForCurrentUser() },
      params.cursor,
      params.limit,
    );
  }
  const { duplicatesOnly, ...query } = params;
  const page = await apiRequest<Page<MediaSummary>>("/media", { query });
  if (!duplicatesOnly) return page;
  return { ...page, items: page.items.filter((m) => m.duplicate_of_media_id != null) };
}

export async function get(id: number): Promise<MediaOut> {
  if (API_MODE === "fixtures") return fixtures.get(id);
  return apiRequest<MediaOut>(`/media/${id}`);
}

export async function attach(id: number, shootingId: number): Promise<MediaOut> {
  if (API_MODE === "fixtures") return fixtures.attach(id, shootingId);
  return apiRequest<MediaOut>(`/media/${id}/attach`, {
    method: "POST",
    json: { shooting_id: shootingId },
  });
}

/** Utilisé par `AuthImage` : en mode live, `thumb_url` peut être un chemin API à
 * authentifier — voir la note d'architecture dans `implementation.md`. */
export async function fetchVariantBlob(id: number, variant: MediaVariant): Promise<Blob> {
  return apiFetchBlob(`/media/${id}/file/${variant}`);
}

/** URL d'aperçu (filigrané) pour la fiche média — data URI simulée en fixtures, chemin
 * d'API authentifié (`AuthImage`) en mode live. */
export function previewUrl(id: number): string {
  if (API_MODE === "fixtures") return fixtures.previewUrl(id);
  return `/media/${id}/file/preview`;
}
