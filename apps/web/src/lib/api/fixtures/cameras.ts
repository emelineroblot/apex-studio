import type { CameraOut, CameraPatch, CameraPatchResponse } from "@/lib/api/types";
import { cameras, media, shootings } from "@/lib/api/fixtures/db";
import { delay, nextId, notFound } from "@/lib/api/fixtures/utils";

export async function list(): Promise<CameraOut[]> {
  await delay(180);
  return cameras;
}

/**
 * Simule §3-F.3 : recalcule `shot_at = shot_at_exif + clock_offset_seconds` pour les
 * médias non rattachés de ce boîtier et les rattache si l'horodatage corrigé tombe dans
 * la plage d'un shooting. Aucun champ de comptage n'existe dans `CameraPatchResponse`
 * (contrat) : le nombre de photos re-rattachées se lit côté écran en comparant
 * `GET /media?unattached=true` avant/après (voir `implementation.md`).
 */
export async function update(id: number, payload: CameraPatch): Promise<CameraPatchResponse> {
  await delay(400);
  const camera = cameras.find((c) => c.id === id);
  if (!camera) notFound("Ce boîtier");

  const offsetChanged =
    payload.clock_offset_seconds != null && payload.clock_offset_seconds !== camera.clock_offset_seconds;
  Object.assign(camera, payload);

  let reattachJobId: number | null = null;
  if (offsetChanged) {
    reattachJobId = nextId();
    for (const item of media) {
      if (item.attachment_status !== "unattached") continue;
      if (item.exif.camera_id !== camera.id) continue;
      if (!item.shot_at_exif) continue;
      const epoch = Date.parse(`${item.shot_at_exif}Z`) + camera.clock_offset_seconds * 1000;
      const match = shootings.find((s) => {
        const start = Date.parse(s.starts_at);
        const end = Date.parse(s.ends_at);
        return epoch >= start && epoch <= end;
      });
      if (match) {
        item.shot_at = new Date(epoch).toISOString();
        item.shooting_id = match.id;
        item.attachment_status = "shooting_attached";
        item.attachment_source = "pipeline_time";
        item.attachment_detail = null;
      }
    }
  }

  return { camera, reattach_job_id: reattachJobId };
}
