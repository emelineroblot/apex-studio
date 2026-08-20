import { API_MODE } from "@/lib/env";
import { apiFetchBlob, apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/media";
import { currentUserId, visibleShootingIdsForCurrentUser } from "@/lib/api/fixtures/access";
import type { IngestStatus, MediaOut, MediaSummary, MediaVariant, Page } from "@/lib/api/types";

export type MediaListParams = {
  shooting_id?: number | null;
  status?: IngestStatus | null;
  batch_id?: number | null;
  unattached?: boolean;
  quarantined?: boolean;
  cursor?: string | null;
  limit?: number;
  /**
   * `GET /media?duplicates=true` — désormais dans le contrat (`services/api/openapi.json`,
   * régénéré ce lot) : par défaut (`false`/omis) les doublons sont exclus de la liste,
   * `true` **n'affiche que** les doublons (jamais mélangés aux non-doublons sur la même
   * page, symétrique à `unattached`/`quarantined`). Un doublon reste consultable
   * individuellement via `get(id)` quel que soit ce paramètre.
   */
  duplicates?: boolean;
  /**
   * `GET /media?series=collapsed|all` — désormais dans le contrat. `collapsed` (défaut
   * backend) : hors-série + un seul représentant par rafale (critère d'acceptation J1
   * « une rafale est regroupée en série et n'affiche qu'un représentant »). `all` : tous
   * les membres, pour ouvrir une série complète depuis sa fiche.
   */
  series?: "collapsed" | "all";
};

export async function list(params: MediaListParams = {}): Promise<Page<MediaSummary>> {
  if (API_MODE === "fixtures") {
    return fixtures.list(
      {
        ...params,
        visibleShootingIds: visibleShootingIdsForCurrentUser(),
        currentUserId: currentUserId(),
      },
      params.cursor,
      params.limit,
    );
  }
  return apiRequest<Page<MediaSummary>>("/media", { query: params });
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

/** URL de vignette pour un média identifié par id seul (`MediaOut` n'expose pas
 * `thumb_url`, contrairement à `MediaSummary`) — utilisé pour afficher le maître d'un
 * doublon dans l'onglet « Doublons » (`DuplicatePairCard`). */
export function thumbUrl(id: number): string {
  if (API_MODE === "fixtures") return fixtures.thumbUrl(id);
  return `/media/${id}/file/thumb`;
}
