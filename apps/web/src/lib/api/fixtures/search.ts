import type { MediaSummary, SearchResponse } from "@/lib/api/types";
import type { SearchFilters } from "@/lib/search/engine";
import { runSearch } from "@/lib/search/engine";
import { searchIndex, searchLabelResolvers } from "@/lib/api/fixtures/searchIndex";
import { delay } from "@/lib/api/fixtures/utils";

function toMediaSummary(entry: ReturnType<typeof searchIndex>[number]): MediaSummary {
  return {
    id: entry.id,
    thumb_url: entry.thumb_url,
    shot_at: entry.shot_at,
    ingest_status: entry.ingest_status,
    attachment_status: entry.attachment_status,
    shooting_id: entry.shooting_id,
    is_simulated: entry.is_simulated,
    duplicate_of_media_id: entry.duplicate_of_media_id,
    series_id: entry.series_id,
    series_member_count: entry.series_member_count,
  };
}

export async function search(
  filters: SearchFilters,
  cursor: string | null | undefined,
  limit: number,
): Promise<SearchResponse> {
  await delay(220);
  const result = runSearch(searchIndex(), filters, searchLabelResolvers, cursor, limit);
  return {
    items: result.items.map(toMediaSummary),
    facets: result.facets,
    total: result.total,
    next_cursor: result.next_cursor,
    took_ms: result.took_ms,
  };
}
