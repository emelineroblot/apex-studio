/**
 * Jeu de recherche (mode "fixtures") — combine les médias curés de `db.ts` (cohérence avec
 * `/library`) et un lot synthétique déterministe (§ brief : « le jeu de démo comptera
 * ~8 000 médias ») pour que `/search` ait des facettes et une pagination réellement
 * démontrables, pas 18 lignes. Le volume réel à 8 000 est un sujet de **performance
 * backend** (`tests/search/test_perf.py`, `docs/search-perf.md`) — ce module reste modeste
 * (quelques centaines d'entrées) pour ne pas alourdir le bundle/tests frontend, la logique
 * de facettes/pagination (`lib/search/engine.ts`) étant, elle, indépendante du volume.
 *
 * Génération à **graine fixe** (mulberry32) — reproductible d'une session à l'autre, comme
 * `apex/demo/synthetic_plates.py` côté backend (§3-J.5 du plan).
 */
import type { SearchIndexEntry } from "@/lib/search/engine";
import { cameras, circuits, clients, drivers, engagements, media, mediaThumbUrl, shootings, teams } from "@/lib/api/fixtures/db";
import { placeholderImage } from "@/lib/api/fixtures/utils";

function mulberry32(seed: number): () => number {
  let a = seed;
  return function random() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const LENS_POOL = [
  "RF 70-200mm F2.8L",
  "RF 100-500mm F4.5-7.1L",
  "Z 70-200mm f/2.8",
  "Z 400mm f/2.8",
  "RF 24-70mm F2.8L",
];
const ISO_POOL = [100, 200, 400, 640, 800, 1250, 1600, 3200, 6400];
const FOCAL_POOL = [24, 35, 70, 135, 200, 300, 400, 500];
const CAPTION_POOL = [
  "Freinage au virage 3",
  "Sortie de stand",
  "Sous la pluie",
  "Départ groupé",
  "Embarquée paddock",
  "Drapeau à damier",
  "Duel pour le podium",
  "Ravitaillement",
  "Vibrations de chaleur en ligne droite",
  "Reconnaissance du tracé",
];
const KEYWORD_POOL = ["virage", "pluie", "depart", "paddock", "podium", "stand", "embouteillage", "vitesse"];

function deriveFromCuratedMedia(): SearchIndexEntry[] {
  // `series_member_count` : même règle que `db.ts::toSummary` — porté par tout membre
  // d'une série (pas seulement le représentant), recalculé en direct sur `media`.
  const memberCount = (seriesId: number) => media.filter((m) => m.series_id === seriesId).length;

  return media.map((m) => {
    const teamIds = new Set<number>();
    const driverIds = new Set<number>();
    const carNumbers = new Set<string>();
    for (const link of m.engagements) {
      carNumbers.add(link.car_number);
      const full = engagements.find((e) => e.id === link.engagement_id);
      if (full?.team_id != null) teamIds.add(full.team_id);
      if (full?.driver_id != null) driverIds.add(full.driver_id);
    }
    const shooting = m.shooting_id != null ? shootings.find((s) => s.id === m.shooting_id) : undefined;
    return {
      id: m.id,
      thumb_url: mediaThumbUrl(m),
      shot_at: m.shot_at,
      ingest_status: m.ingest_status,
      attachment_status: m.attachment_status,
      shooting_id: m.shooting_id,
      client_id: shooting?.client_id ?? null,
      circuit_id: shooting?.circuit_id ?? null,
      camera_id: m.exif.camera_id,
      lens: m.exif.lens_model,
      iso: m.exif.iso,
      focal_length: m.exif.focal_length,
      team_ids: [...teamIds],
      driver_ids: [...driverIds],
      car_numbers: [...carNumbers],
      caption: m.caption,
      keywords: m.keywords ?? [],
      series_id: m.series_id,
      series_member_count: m.series_id != null ? memberCount(m.series_id) : null,
      is_series_representative: m.is_series_representative,
      duplicate_of_media_id: m.duplicate_of_media_id,
      is_simulated: m.is_simulated,
    };
  });
}

const SYNTHETIC_COUNT = 260;
const SYNTHETIC_ID_BASE = 2001;

function generateSynthetic(): SearchIndexEntry[] {
  const random = mulberry32(20260821); // graine fixe — date du jalon, reproductible.
  const out: SearchIndexEntry[] = [];
  let seriesCounter = 9000;

  for (let i = 0; i < SYNTHETIC_COUNT; i += 1) {
    const id = SYNTHETIC_ID_BASE + i;
    const shooting = shootings[Math.floor(random() * shootings.length)];
    const shootingEngagements = engagements.filter((e) => e.shooting_id === shooting.id);
    const camera = cameras[Math.floor(random() * cameras.length)];
    const startMs = Date.parse(shooting.starts_at);
    const endMs = Date.parse(shooting.ends_at);
    const shotAt = new Date(startMs + random() * Math.max(1, endMs - startMs)).toISOString();

    const engagementCount = shootingEngagements.length === 0 ? 0 : random() < 0.12 ? 2 : 1;
    const picked: typeof shootingEngagements = [];
    for (let k = 0; k < engagementCount; k += 1) {
      const candidate = shootingEngagements[Math.floor(random() * shootingEngagements.length)];
      if (candidate && !picked.includes(candidate)) picked.push(candidate);
    }

    const attachmentRoll = random();
    const attachment_status =
      picked.length > 0
        ? "engagement_attached"
        : attachmentRoll < 0.7
          ? "shooting_attached"
          : attachmentRoll < 0.9
            ? "unattached"
            : "pending_review";

    // Un groupe de 3 sur 24 (petites rafales dispersées) pour que le repli « rafales
    // groupées / toutes » ait un effet observable à l'échelle du jeu synthétique aussi.
    const isBurstStart = i % 24 === 0 && i + 2 < SYNTHETIC_COUNT;
    const burstIndex = i % 24;
    const inBurst = burstIndex < 3 && i - burstIndex + 2 < SYNTHETIC_COUNT;
    const seriesId = inBurst ? (isBurstStart ? (seriesCounter += 1) : seriesCounter) : null;

    const client = shooting.client_id != null ? shooting.client_id : null;
    const tone = ["#1e2434", "#22304a", "#2a3244", "#1c2d3c"][i % 4];

    out.push({
      id,
      thumb_url: placeholderImage(`Média #${id}`, { tone, sub: "Jeu simulé" }),
      shot_at: shotAt,
      ingest_status: "ingested",
      attachment_status,
      shooting_id: shooting.id,
      client_id: client,
      circuit_id: shooting.circuit_id,
      camera_id: camera.id,
      lens: LENS_POOL[Math.floor(random() * LENS_POOL.length)],
      iso: ISO_POOL[Math.floor(random() * ISO_POOL.length)],
      focal_length: FOCAL_POOL[Math.floor(random() * FOCAL_POOL.length)],
      team_ids: picked.map((e) => e.team_id).filter((v): v is number => v != null),
      driver_ids: picked.map((e) => e.driver_id).filter((v): v is number => v != null),
      car_numbers: picked.map((e) => e.car_number),
      caption: CAPTION_POOL[Math.floor(random() * CAPTION_POOL.length)],
      keywords: [KEYWORD_POOL[Math.floor(random() * KEYWORD_POOL.length)]],
      series_id: seriesId,
      series_member_count: seriesId != null ? 3 : null,
      is_series_representative: seriesId != null ? burstIndex === 0 : true,
      duplicate_of_media_id: null,
      is_simulated: true,
    });
  }
  return out;
}

let cachedIndex: SearchIndexEntry[] | null = null;

/** Reconstruit à chaque appel de `db.media` (peut grossir en cours de session, § upload
 * simulé) — le lot synthétique, lui, est mis en cache : coûteux à régénérer, immuable. */
export function searchIndex(): SearchIndexEntry[] {
  if (!cachedIndex) cachedIndex = generateSynthetic();
  return [...deriveFromCuratedMedia(), ...cachedIndex];
}

/** Résolveurs de libellés — utilisés par `lib/search/engine.ts::computeFacets`. */
export const searchLabelResolvers = {
  shooting: (id: number) => shootings.find((s) => s.id === id)?.title ?? null,
  client: (id: number) => clients.find((c) => c.id === id)?.name ?? null,
  team: (id: number) => teams.find((t) => t.id === id)?.name ?? null,
  driver: (id: number) => drivers.find((d) => d.id === id)?.full_name ?? null,
  circuit: (id: number) => circuits.find((c) => c.id === id)?.name ?? null,
  camera: (id: number) => {
    const camera = cameras.find((c) => c.id === id);
    return camera ? `${camera.make} ${camera.model}` : null;
  },
};
