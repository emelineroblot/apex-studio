/**
 * `GET /stats/auto-attach-rate` (§ tâche 5 — « l'indicateur produit du jalon, il doit être
 * visible, pas enterré »). Calculé depuis `media.attachment_source` (§3-F.3/§3-J.3) : chaque
 * média ingéré et non-doublon a **exactement une** des quatre origines de rattachement —
 * `pipeline_time` (fenêtre horaire), `pipeline_ocr` (numéro lu automatiquement), `human`
 * (rattachement manuel ou validation en file de revue) ou aucune (`unattached`). Bucketer
 * ainsi rend `total = auto_time + auto_ocr + human + unattached` vrai par construction,
 * jamais recalculé « à la main » côté écran (même invariant que le futur dashboard J3,
 * § contrat « lu depuis la base, jamais recalculé dans l'UI »).
 */
import type { AutoAttachRate } from "@/lib/api/types";
import { media } from "@/lib/api/fixtures/db";
import { delay } from "@/lib/api/fixtures/utils";

export async function autoAttachRate(params: {
  shooting_id?: number | null;
  from?: string | null;
  to?: string | null;
}): Promise<AutoAttachRate> {
  await delay(180);
  let scoped = media.filter((m) => m.ingest_status === "ingested" && m.duplicate_of_media_id == null);
  if (params.shooting_id != null) scoped = scoped.filter((m) => m.shooting_id === params.shooting_id);
  if (params.from) scoped = scoped.filter((m) => (m.shot_at ?? "") >= params.from!);
  if (params.to) scoped = scoped.filter((m) => (m.shot_at ?? "") <= params.to!);

  const total = scoped.length;
  const auto_time = scoped.filter((m) => m.attachment_source === "pipeline_time").length;
  const auto_ocr = scoped.filter((m) => m.attachment_source === "pipeline_ocr").length;
  const human = scoped.filter((m) => m.attachment_source === "human").length;
  const unattached = scoped.filter((m) => m.attachment_source == null).length;
  const rate = total > 0 ? (auto_time + auto_ocr) / total : 0;

  return { total, auto_time, auto_ocr, human, unattached, rate };
}
