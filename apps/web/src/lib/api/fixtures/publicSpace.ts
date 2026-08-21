/**
 * Espace client en mode "fixtures" — une collection partagée, jouable sans backend.
 *
 * Rejoue les règles qui comptent pour l'écran, et **seulement** celles-là : une sélection
 * qui se fige à la validation, une livraison qui passe par `building` avant `ready`. Un
 * mode fixtures qui livrerait l'archive instantanément masquerait précisément l'état que
 * l'interface doit savoir afficher.
 */
import { ApiError } from "@/lib/api/errors";
import { delay, placeholderImage } from "@/lib/api/fixtures/utils";
import type {
  PublicCollectionRef,
  PublicCollectionResponse,
  PublicDeliveryStatusResponse,
  PublicMediaItem,
  PublicSelectionItemResponse,
  PublicSelectionResponse,
  PublicSelectionValidateResponse,
  PublicSessionResponse,
} from "@/lib/api/types";

/** Jeton reconnu en mode fixtures. Tout autre jeton simule un lien mort — c'est le seul
 * moyen d'exercer l'écran « ce lien n'est plus valide » sans backend. */
export const FIXTURE_TOKEN = "demo";
const EXPIRED_TOKEN = "expire";

const COLLECTION: PublicCollectionRef = {
  title: "Grand Prix de Nogaro — écurie Vermeil",
  description: "Vos images du week-end. Cochez celles que vous souhaitez recevoir en haute définition.",
  item_count: 12,
  studio_name: "Studio Chicane",
};

const CAR_NUMBERS = ["12", "12", "27", "27", "27", "44", "44", "5", "5", "88", "88", "3"];

const ITEMS: PublicMediaItem[] = CAR_NUMBERS.map((number, index) => {
  const mediaId = 5000 + index;
  return {
    media_id: mediaId,
    preview_url: `/public/media/${mediaId}/file/preview`,
    thumb_url: `/public/media/${mediaId}/file/thumb`,
    shot_at: new Date(Date.UTC(2026, 4, 16, 10, 12 + index * 3)).toISOString(),
    car_numbers: [number],
    selected: false,
    comment: null,
  };
});

const selection = new Map<number, string | null>();
let selectionValidated = false;
let validatedAt: number | null = null;

/** Temps de « préparation » simulé : la livraison n'est pas prête à la seconde où le
 * client valide, et l'écran doit savoir montrer cette attente. */
const BUILD_DURATION_MS = 6000;

export function resetFixtureState(): void {
  selection.clear();
  selectionValidated = false;
  validatedAt = null;
}

function linkExpired(): never {
  throw new ApiError(410, {
    code: "link_expired",
    message: "Ce lien de partage n'est plus valide.",
  });
}

function assertOpen(): void {
  if (selectionValidated) {
    throw new ApiError(409, {
      code: "selection_validated",
      message: "Votre sélection a été validée : elle ne peut plus être modifiée.",
    });
  }
}

export async function openSession(token: string): Promise<PublicSessionResponse> {
  await delay(320);
  if (token === EXPIRED_TOKEN) linkExpired();
  if (token !== FIXTURE_TOKEN) {
    throw new ApiError(404, { code: "not_found", message: "Ressource introuvable." });
  }
  return {
    access_token: `fixture-client-token-${token}`,
    expires_in: 1800,
    collection: COLLECTION,
  };
}

export async function getCollection(
  params: { cursor?: string | null; limit?: number; selected_only?: boolean } = {},
): Promise<PublicCollectionResponse> {
  await delay(240);
  const items = ITEMS.filter((item) => !params.selected_only || selection.has(item.media_id)).map(
    (item) => ({
      ...item,
      selected: selection.has(item.media_id),
      comment: selection.get(item.media_id) ?? null,
    }),
  );
  return { collection: COLLECTION, items, next_cursor: null };
}

export async function selectMedia(
  mediaId: number,
  comment: string | null,
): Promise<PublicSelectionItemResponse> {
  await delay(120);
  assertOpen();
  const cleaned = comment?.trim() || null;
  selection.set(mediaId, cleaned);
  return { selected: true, comment: cleaned };
}

export async function deselectMedia(mediaId: number): Promise<void> {
  await delay(120);
  assertOpen();
  selection.delete(mediaId);
}

export async function getSelection(): Promise<PublicSelectionResponse> {
  await delay(180);
  const items = [...selection.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([media_id, comment]) => ({ media_id, comment }));
  return {
    status: selectionValidated ? "validated" : "open",
    count: items.length,
    items,
  };
}

export async function validateSelection(): Promise<PublicSelectionValidateResponse> {
  await delay(400);
  if (selection.size === 0) {
    throw new ApiError(409, {
      code: "empty_selection",
      message: "Choisissez au moins une photo avant de valider.",
    });
  }
  if (!selectionValidated) {
    selectionValidated = true;
    validatedAt = Date.now();
  }
  return { status: "validated", delivery: { id: 1, status: "pending" } };
}

export async function getDelivery(): Promise<PublicDeliveryStatusResponse> {
  await delay(200);
  if (!selectionValidated || validatedAt === null) {
    return { status: "pending", item_count: null, byte_size: null, ready: false };
  }
  const elapsed = Date.now() - validatedAt;
  if (elapsed < BUILD_DURATION_MS) {
    return { status: "building", item_count: selection.size, byte_size: null, ready: false };
  }
  return {
    status: "ready",
    item_count: selection.size,
    byte_size: selection.size * 8_400_000,
    ready: true,
  };
}

export async function downloadArchive(): Promise<Blob> {
  await delay(500);
  const manifest = [...selection.keys()].map((id) => `photo-${id}.jpg`).join("\n");
  return new Blob([`Archive de démonstration\n\n${manifest}\n`], { type: "application/zip" });
}

export async function fetchImage(path: string): Promise<Blob> {
  await delay(80);
  const mediaId = Number.parseInt(path.split("/")[3] ?? "0", 10);
  const index = Math.max(0, mediaId - 5000);
  const svg = placeholderImage(`#${CAR_NUMBERS[index % CAR_NUMBERS.length]}`, {
    tone: ["#2a3244", "#3b2f45", "#1f3a3d", "#402b2b"][index % 4],
    sub: "Studio Chicane — apercu",
  });
  const raw = svg.replace("data:image/svg+xml;utf8,", "");
  return new Blob([decodeURIComponent(raw)], { type: "image/svg+xml" });
}
