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
  /** Filtre client (pas dans le contrat, voir `resources/media.ts`) — page courante seulement. */
  duplicatesOnly?: boolean;
  visibleShootingIds?: number[] | null;
};

export async function list(
  filters: MediaListFilters,
  cursor?: string | null,
  limit = 60,
): Promise<Page<MediaSummary>> {
  await delay();
  let scoped = media;
  if (filters.visibleShootingIds) {
    const allowed = new Set(filters.visibleShootingIds);
    scoped = scoped.filter((m) => m.shooting_id != null && allowed.has(m.shooting_id));
  }
  if (filters.shooting_id != null) scoped = scoped.filter((m) => m.shooting_id === filters.shooting_id);
  if (filters.status) scoped = scoped.filter((m) => m.ingest_status === filters.status);
  if (filters.batch_id != null) scoped = scoped.filter((m) => m.batch_id === filters.batch_id);
  if (filters.unattached) scoped = scoped.filter((m) => m.attachment_status === "unattached");
  if (filters.quarantined) scoped = scoped.filter((m) => m.ingest_status === "quarantined");
  if (filters.duplicatesOnly) scoped = scoped.filter((m) => m.duplicate_of_media_id != null);

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
