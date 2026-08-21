import type { CollectionAddItemsResponse, CollectionCreate, CollectionOut, Page } from "@/lib/api/types";
import type { SearchFilters } from "@/lib/search/engine";
import { filterEntries } from "@/lib/search/engine";
import { collections } from "@/lib/api/fixtures/db";
import { searchIndex } from "@/lib/api/fixtures/searchIndex";
import { delay, nextId, notFound, paginate } from "@/lib/api/fixtures/utils";

export async function list(cursor: string | null | undefined, limit: number): Promise<Page<CollectionOut>> {
  await delay(200);
  const sorted = [...collections].sort((a, b) => b.id - a.id);
  return paginate(sorted, cursor, limit);
}

export async function create(payload: CollectionCreate): Promise<CollectionOut> {
  await delay(300);
  const created: CollectionOut = {
    id: nextId(),
    client_id: payload.client_id,
    shooting_id: payload.shooting_id ?? null,
    title: payload.title,
    description: payload.description ?? null,
    status: "draft",
    published_at: null,
    created_by: 1,
    items: [],
  };
  collections.push(created);
  return created;
}

export async function get(id: number): Promise<CollectionOut> {
  await delay(150);
  const found = collections.find((c) => c.id === id);
  if (!found) notFound("Cette collection");
  return found;
}

export async function addItems(
  id: number,
  payload: { media_ids?: number[] | null; from_search?: SearchFilters | null },
): Promise<CollectionAddItemsResponse> {
  await delay(350);
  const collection = collections.find((c) => c.id === id);
  if (!collection) notFound("Cette collection");

  let candidateIds: number[];
  if (payload.from_search) {
    candidateIds = filterEntries(searchIndex(), payload.from_search).map((e) => e.id);
  } else {
    candidateIds = payload.media_ids ?? [];
  }

  const existing = new Set(collection.items.map((i) => i.media_id));
  let added = 0;
  let skipped = 0;
  let position = collection.items.length;
  for (const mediaId of candidateIds) {
    if (existing.has(mediaId)) {
      skipped += 1;
      continue;
    }
    collection.items.push({ media_id: mediaId, position });
    existing.add(mediaId);
    position += 1;
    added += 1;
  }
  return { added, skipped_duplicates: skipped };
}

export async function removeItem(id: number, mediaId: number): Promise<void> {
  await delay(200);
  const collection = collections.find((c) => c.id === id);
  if (!collection) notFound("Cette collection");
  collection.items = collection.items
    .filter((i) => i.media_id !== mediaId)
    .map((item, index) => ({ ...item, position: index }));
}

export async function publish(id: number): Promise<CollectionOut> {
  await delay(300);
  const collection = collections.find((c) => c.id === id);
  if (!collection) notFound("Cette collection");
  collection.status = "published";
  collection.published_at = new Date().toISOString();
  return collection;
}
