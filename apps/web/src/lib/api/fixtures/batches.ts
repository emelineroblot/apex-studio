/**
 * Simule le pipeline d'ingestion (§ Décision E, F du plan) : chaque appel à `getStatus()`
 * fait avancer d'un cran la file des fichiers `processing` de ce lot — comme le contrat
 * le précise (« déclenche un tick si la file n'est pas vide »), le polling 1 s de l'écran
 * `batches/[id]` joue ici le rôle du worker.
 */
import type {
  BatchCloseResponse,
  BatchCreateResponse,
  BatchStatusResponse,
  FileUploadResponse,
  MediaOut,
  PipelineEventOut,
} from "@/lib/api/types";
import { batches, media, shootings, type FixtureBatch, type MediaFixture } from "@/lib/api/fixtures/db";
import { currentUserId } from "@/lib/api/fixtures/access";
import { ApiError } from "@/lib/api/errors";
import { delay, nextId, notFound } from "@/lib/api/fixtures/utils";

const uploadedKeys = new Map<string, number>(); // `${batchId}:${idempotencyKey}` -> media_id
const pipelineEvents = new Map<number, PipelineEventOut[]>(); // batch_id -> journal

function logEvent(batchId: number, step: string, status: string, message: string | null = null) {
  const list = pipelineEvents.get(batchId) ?? [];
  list.push({ step, status, duration_ms: null, message, created_at: new Date().toISOString() });
  pipelineEvents.set(batchId, list);
}

export async function create(payload: {
  expected_count: number;
  shooting_hint_id?: number | null;
}): Promise<BatchCreateResponse> {
  await delay(250);
  const batch: FixtureBatch = {
    id: nextId(),
    expected_count: payload.expected_count,
    received_count: 0,
    status: "open",
    shooting_hint_id: payload.shooting_hint_id ?? null,
    started_at: new Date().toISOString(),
  };
  batches.push(batch);
  logEvent(batch.id, "batch", "opened", `Lot ouvert, ${payload.expected_count} fichier(s) annoncé(s).`);
  return { id: batch.id, status: batch.status, expected_count: batch.expected_count };
}

function deterministicOutcome(
  index: number,
  shootingHintId: number | null,
): Pick<
  MediaOut,
  | "ingest_status"
  | "quarantine_reason"
  | "quarantine_detail"
  | "attachment_status"
  | "attachment_source"
  | "attachment_detail"
  | "shooting_id"
  | "duplicate_of_media_id"
> {
  if (index > 0 && index % 11 === 0) {
    return {
      ingest_status: "quarantined",
      quarantine_reason: "dimensions_out_of_range",
      // Clé alignée sur le vrai backend (`expected`, pas `min_expected` — jamais émis par
      // l'API, § `implementation.md`).
      quarantine_detail: { width: 64, height: 48, expected: "[640..12000]" },
      attachment_status: "unattached",
      attachment_source: null,
      attachment_detail: null,
      shooting_id: null,
      duplicate_of_media_id: null,
    };
  }
  if (index > 0 && index % 9 === 0) {
    return {
      ingest_status: "ingested",
      quarantine_reason: null,
      quarantine_detail: null,
      attachment_status: "unattached",
      attachment_source: null,
      attachment_detail: { reason: "no_exif_timestamp" },
      shooting_id: null,
      duplicate_of_media_id: null,
    };
  }
  return {
    ingest_status: "ingested",
    quarantine_reason: null,
    quarantine_detail: null,
    attachment_status: shootingHintId ? "shooting_attached" : "unattached",
    attachment_source: shootingHintId ? "pipeline_time" : null,
    attachment_detail: shootingHintId ? null : { reason: "no_exif_timestamp" },
    shooting_id: shootingHintId,
    duplicate_of_media_id: null,
  };
}

export async function uploadFile(
  batchId: number,
  file: { name: string; size: number },
  idempotencyKey: string,
): Promise<FileUploadResponse> {
  await delay(180);
  const batch = batches.find((b) => b.id === batchId);
  if (!batch) notFound("Ce lot");
  if (batch.status === "closed") {
    throw new ApiError(409, { code: "batch_closed", message: "Ce lot est déjà clos." });
  }

  const dedupeKey = `${batchId}:${idempotencyKey}`;
  const existingId = uploadedKeys.get(dedupeKey);
  if (existingId) {
    return { media_id: existingId, status: "uploaded", duplicate: false };
  }

  const id = nextId();
  const item: MediaFixture = {
    id,
    batch_id: batchId,
    // Bac « à rattacher » filtré par déposant (§ `fixtures/media.ts`, revue J1) : un upload
    // simulé appartient à l'utilisateur courant, pas à un compte arbitraire.
    uploaded_by: currentUserId() ?? 1,
    original_filename: file.name,
    byte_size: file.size,
    mime: file.name.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg",
    width: null,
    height: null,
    shot_at_exif: null,
    shot_at: null,
    exif: {
      camera_id: null,
      lens_model: null,
      iso: null,
      shutter_speed_sec: null,
      shutter_speed_label: null,
      aperture: null,
      focal_length: null,
      gps_lat: null,
      gps_lon: null,
      exif_raw: null,
    },
    phash: null,
    sharpness: null,
    series_id: null,
    is_series_representative: true,
    duplicate_of_media_id: null,
    ingest_status: "uploaded",
    quarantine_reason: null,
    quarantine_detail: null,
    attachment_status: "unattached",
    attachment_source: null,
    attachment_detail: null,
    shooting_id: null,
    is_simulated: true,
    caption: null,
    keywords: null,
    engagements: [],
    events: ["upload"],
  };
  media.push(item);
  uploadedKeys.set(dedupeKey, id);
  batch.received_count += 1;
  logEvent(batchId, "upload", "ok", `${file.name} déposé (${Math.round(file.size / 1024)} Ko).`);
  return { media_id: id, status: "uploaded", duplicate: false };
}

export async function close(batchId: number): Promise<BatchCloseResponse> {
  await delay(200);
  const batch = batches.find((b) => b.id === batchId);
  if (!batch) notFound("Ce lot");
  batch.status = "processing";
  const inBatch = media.filter((m) => m.batch_id === batchId);
  for (const item of inBatch) {
    item.ingest_status = "processing";
    item.events.push("queued");
  }
  logEvent(batchId, "batch", "processing", "Traitement démarré.");
  return { id: batch.id, status: batch.status };
}

const TICK_SIZE = 3;

export async function getStatus(batchId: number): Promise<BatchStatusResponse> {
  await delay(150);
  const batch = batches.find((b) => b.id === batchId);
  if (!batch) notFound("Ce lot");

  const inBatch = media.filter((m) => m.batch_id === batchId);
  const processing = inBatch.filter((m) => m.ingest_status === "processing");
  const shootingHint = batch.shooting_hint_id
    ? (shootings.find((s) => s.id === batch.shooting_hint_id)?.id ?? null)
    : null;

  processing.slice(0, TICK_SIZE).forEach((item, i) => {
    const outcome = deterministicOutcome(item.id + i, shootingHint);
    Object.assign(item, outcome);
    item.width = outcome.ingest_status === "quarantined" ? 64 : 6000;
    item.height = outcome.ingest_status === "quarantined" ? 48 : 4000;
    item.shot_at_exif = new Date().toISOString().slice(0, 19);
    item.shot_at = outcome.shooting_id ? new Date().toISOString() : null;
    item.events.push(
      outcome.ingest_status === "quarantined" ? "integrity:quarantined" : "integrity:ok",
      "exif",
      "hash",
      outcome.shooting_id ? "attach_time:matched" : "attach_time:unmatched",
      "derivatives",
    );
    logEvent(
      batchId,
      "ingest",
      outcome.ingest_status === "quarantined" ? "quarantined" : "ok",
      `Média #${item.id} — ${outcome.ingest_status === "quarantined" ? "quarantaine" : "ingéré"}.`,
    );
  });

  const allDone = inBatch.length > 0 && inBatch.every((m) => m.ingest_status !== "processing" && m.ingest_status !== "uploaded");
  if (allDone && batch.status !== "closed" && batch.received_count >= batch.expected_count) {
    batch.status = "closed";
  }

  const counts = {
    uploaded: inBatch.filter((m) => m.ingest_status === "uploaded").length,
    processing: inBatch.filter((m) => m.ingest_status === "processing").length,
    ingested: inBatch.filter((m) => m.ingest_status === "ingested").length,
    quarantined: inBatch.filter((m) => m.ingest_status === "quarantined").length,
  };
  const done = inBatch.length === batch.expected_count && counts.processing === 0 && counts.uploaded === 0;
  const progress = batch.expected_count > 0 ? (counts.ingested + counts.quarantined) / batch.expected_count : 0;

  return {
    id: batch.id,
    expected_count: batch.expected_count,
    received_count: batch.received_count,
    counts,
    attached_count: inBatch.filter(
      (m) => m.attachment_status === "shooting_attached" || m.attachment_status === "engagement_attached",
    ).length,
    duplicate_count: inBatch.filter((m) => m.duplicate_of_media_id != null).length,
    progress: Math.min(1, progress),
    missing_count: Math.max(0, batch.expected_count - batch.received_count),
    done,
    events: [...(pipelineEvents.get(batchId) ?? [])].slice(-30).reverse(),
  };
}
