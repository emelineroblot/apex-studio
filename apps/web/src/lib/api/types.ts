/**
 * Alias de confort vers les schémas générés (`schema.d.ts`, GÉNÉRÉ — ne pas éditer).
 * Un seul endroit à modifier si l'OpenAPI change de nommage.
 */
import type { components } from "./schema.d.ts";

type Schemas = components["schemas"];

export type Role = Schemas["UserOut"]["role"];
export type UserOut = Schemas["UserOut"];
export type DemoAccount = Schemas["DemoAccount"];
export type TokenResponse = Schemas["TokenResponse"];

export type ClientOut = Schemas["ClientOut"];
export type ClientCreate = Schemas["ClientCreate"];
export type ClientUpdate = Schemas["ClientUpdate"];

export type CircuitOut = Schemas["CircuitOut"];
export type CircuitCreate = Schemas["CircuitCreate"];

export type DriverOut = Schemas["DriverOut"];
export type DriverCreate = Schemas["DriverCreate"];

export type TeamOut = Schemas["TeamOut"];
export type TeamCreate = Schemas["TeamCreate"];

export type ShootingOut = Schemas["ShootingOut"];
export type ShootingCreate = Schemas["ShootingCreate"];
export type ShootingPatch = Schemas["ShootingPatch"];
export type ShootingSummary = Schemas["ShootingSummary"];
export type ShootingStatus = ShootingOut["status"];
export type StaffMember = Schemas["StaffMember"];

export type EngagementOut = Schemas["EngagementOut"];
export type EngagementCreate = Schemas["EngagementCreate"];
export type EngagementPatch = Schemas["EngagementPatch"];
export type EngagementImportResult = Schemas["EngagementImportResult"];
export type EngagementImportError = Schemas["EngagementImportError"];

export type BatchCreateResponse = Schemas["BatchCreateResponse"];
export type FileUploadResponse = Schemas["FileUploadResponse"];
export type BatchStatusResponse = Schemas["BatchStatusResponse"];
export type BatchStatusCounts = Schemas["BatchStatusCounts"];
export type BatchCloseResponse = Schemas["BatchCloseResponse"];

export type MediaSummary = Schemas["MediaSummary"];
export type MediaOut = Schemas["MediaOut"];
export type MediaExif = Schemas["MediaExif"];
export type MediaEngagementOut = Schemas["MediaEngagementOut"];
export type IngestStatus = MediaSummary["ingest_status"];
export type AttachmentStatus = MediaSummary["attachment_status"];
export type MediaVariant = "thumb" | "preview" | "hd";
export type PipelineEventOut = Schemas["PipelineEventOut"];

export type CameraOut = Schemas["CameraOut"];
export type CameraPatch = Schemas["CameraPatch"];
export type CameraPatchResponse = Schemas["CameraPatchResponse"];

export type Page<T> = { items: T[]; next_cursor: string | null; total: number | null };

/** Motifs de quarantaine fermés (§ modèle `media.py`, `QUARANTINE_REASONS`). */
export const QUARANTINE_REASONS = [
  "truncated_file",
  "not_an_image",
  "unsupported_mime",
  "dimensions_out_of_range",
  "aspect_ratio_out_of_range",
  "exif_inconsistent",
  "too_large",
  "quota_exceeded",
  "ingest_failed",
  "orphan_object",
] as const;
export type QuarantineReason = (typeof QUARANTINE_REASONS)[number];
