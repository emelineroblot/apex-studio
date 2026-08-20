import Link from "next/link";
import type { MediaOut, MediaSummary } from "@/lib/api/types";
import { formatBytes, formatDateTime } from "@/lib/format";
import { AuthImage } from "@/components/media/AuthImage";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

/**
 * Un doublon **présenté avec son maître** (§ tâche 2) : sans lui, l'onglet « Doublons »
 * n'a pas de sens (un fichier identique déjà ingéré, jamais orphelin). `GET
 * /media?duplicates=true` ne renvoie que les doublons eux-mêmes (`MediaSummary`,
 * `duplicate_of_media_id` non nul) — le maître est chargé séparément par l'appelant
 * (`library/page.tsx`, un `GET /media/{id}` par maître unique) et transmis ici déjà résolu.
 */
export function DuplicatePairCard({
  duplicate,
  master,
  masterThumbUrl,
}: {
  duplicate: MediaSummary;
  master: MediaOut | undefined;
  /** `MediaOut` (fiche détaillée du maître) n'expose pas `thumb_url` — calculée par
   * l'appelant via `mediaApi.thumbUrl(master.id)` (§ `resources/media.ts`). */
  masterThumbUrl: string;
}) {
  return (
    <Card className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="flex flex-1 items-center gap-3">
        <Link href={`/media/${duplicate.id}`} className="shrink-0">
          <div className="h-16 w-24 overflow-hidden rounded-lg bg-ink-100">
            <AuthImage
              src={duplicate.thumb_url}
              alt={`Doublon #${duplicate.id}`}
              className="h-full w-full object-cover"
            />
          </div>
        </Link>
        <div>
          <Badge tone="warn">Copie</Badge>
          <p className="mt-1 text-sm font-semibold text-ink-900">
            <Link href={`/media/${duplicate.id}`} className="hover:text-accent-600">
              Média #{duplicate.id}
            </Link>
          </p>
          <p className="text-xs text-ink-500">
            {duplicate.shot_at ? formatDateTime(duplicate.shot_at) : "Horodatage inconnu"}
          </p>
        </div>
      </div>

      <span className="hidden text-ink-300 sm:block" aria-hidden="true">
        →
      </span>

      <div className="flex flex-1 items-center gap-3">
        {master ? (
          <>
            <Link href={`/media/${master.id}`} className="shrink-0">
              <div className="h-16 w-24 overflow-hidden rounded-lg bg-ink-100">
                <AuthImage
                  src={masterThumbUrl}
                  alt={`Maître #${master.id}`}
                  className="h-full w-full object-cover"
                />
              </div>
            </Link>
            <div>
              <Badge tone="ok">Conservé (maître)</Badge>
              <p className="mt-1 text-sm font-semibold text-ink-900">
                <Link href={`/media/${master.id}`} className="hover:text-accent-600">
                  {master.original_filename}
                </Link>
              </p>
              <p className="text-xs text-ink-500">{formatBytes(master.byte_size)}</p>
            </div>
          </>
        ) : (
          <p className="text-sm text-ink-400">Maître introuvable (#{duplicate.duplicate_of_media_id}).</p>
        )}
      </div>
    </Card>
  );
}
