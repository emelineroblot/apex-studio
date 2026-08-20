import type { IngestStatus, MediaOut, MediaSummary, Page } from "@/lib/api/types";
import { media, mediaThumbUrl, toSummary } from "@/lib/api/fixtures/db";
import { ApiError } from "@/lib/api/errors";
import { delay, notFound, paginate } from "@/lib/api/fixtures/utils";

export type MediaListFilters = {
  shooting_id?: number | null;
  status?: IngestStatus | null;
  batch_id?: number | null;
  unattached?: boolean;
  quarantined?: boolean;
  /** `GET /media?duplicates=true` (contrat réel, § `routers/media.py::list_media`) — par
   * défaut (`false`), les doublons sont exclus, symétrique à `unattached`/`quarantined`. */
  duplicates?: boolean;
  /** `GET /media?series=collapsed|all` (contrat réel) — `collapsed` par défaut : hors-série
   * + un seul représentant par rafale, `all` renvoie tous les membres. */
  series?: "collapsed" | "all";
  visibleShootingIds?: number[] | null;
  /** Id de l'utilisateur courant — voir la clause `uploaded_by` ci-dessous. */
  currentUserId?: number | null;
};

export async function list(
  filters: MediaListFilters,
  cursor?: string | null,
  limit = 60,
): Promise<Page<MediaSummary>> {
  await delay();
  let scoped = media;
  if (filters.visibleShootingIds) {
    // Rejoue `services/access.py::media_visibility_clause` : un média sans shooting
    // (`shooting_id IS NULL`, bac « à rattacher ») reste visible par son déposant, même
    // hors de la liste de shootings affectés — sinon un photographe perd de vue ses
    // propres imports tant qu'ils ne sont pas rattachés (constat revue J1).
    const allowed = new Set(filters.visibleShootingIds);
    scoped = scoped.filter(
      (m) =>
        (m.shooting_id != null && allowed.has(m.shooting_id)) ||
        (filters.currentUserId != null && m.uploaded_by === filters.currentUserId),
    );
  }
  // Rejoue `routers/media.py::list_media` — par défaut, un doublon n'apparaît jamais mélangé
  // aux non-doublons (critère d'acceptation J1 « deux fichiers identiques sont
  // dédoublonnés ») ; `duplicates=true` inverse plutôt que d'annuler le filtre, pour ne
  // jamais les mélanger sur la même page. Absent avant ce lot : la fixture laissait
  // passer les doublons dans l'onglet « Tout », divergence jamais détectée faute de test.
  scoped = scoped.filter((m) =>
    filters.duplicates ? m.duplicate_of_media_id != null : m.duplicate_of_media_id == null,
  );
  // Rejoue `routers/media.py::list_media` — `series=collapsed` (défaut) ne renvoie que les
  // médias hors série et le représentant de chaque série ; `series=all` renvoie tous les
  // membres (zoom sur une série depuis sa fiche).
  if ((filters.series ?? "collapsed") === "collapsed") {
    scoped = scoped.filter((m) => m.series_id == null || m.is_series_representative);
  }
  if (filters.shooting_id != null) scoped = scoped.filter((m) => m.shooting_id === filters.shooting_id);
  if (filters.status) scoped = scoped.filter((m) => m.ingest_status === filters.status);
  if (filters.batch_id != null) scoped = scoped.filter((m) => m.batch_id === filters.batch_id);
  if (filters.unattached) scoped = scoped.filter((m) => m.attachment_status === "unattached");
  if (filters.quarantined) scoped = scoped.filter((m) => m.ingest_status === "quarantined");

  const sorted = [...scoped].sort((a, b) => b.id - a.id);
  const page = paginate(sorted, cursor, limit);
  return { ...page, items: page.items.map(toSummary) };
}

export async function get(id: number): Promise<MediaOut> {
  await delay(150);
  const found = media.find((m) => m.id === id);
  if (!found) notFound("Ce média");
  return found;
}

export function previewUrl(id: number): string {
  const found = media.find((m) => m.id === id);
  if (!found) return "";
  return mediaThumbUrl(found);
}

/** Vignette d'un média identifié par id seul — `MediaOut` (fiche détaillée) n'expose pas
 * `thumb_url` (seul `MediaSummary`, la liste, le fait) : utilisé pour afficher la vignette
 * du **maître** d'un doublon dans l'onglet « Doublons » (`DuplicatePairCard`), où seule
 * `MediaOut` du maître est disponible côté appelant. */
export function thumbUrl(id: number): string {
  const found = media.find((m) => m.id === id);
  if (!found) return "";
  return mediaThumbUrl(found);
}

export async function attach(id: number, shootingId: number): Promise<MediaOut> {
  await delay(300);
  const found = media.find((m) => m.id === id);
  if (!found) notFound("Ce média");
  if (found.ingest_status === "quarantined") {
    throw new ApiError(409, {
      code: "media_quarantined",
      message: "Ce média est en quarantaine, il ne peut pas être rattaché.",
    });
  }
  found.shooting_id = shootingId;
  found.attachment_status = "shooting_attached";
  found.attachment_source = "human";
  found.attachment_detail = null;
  return found;
}
