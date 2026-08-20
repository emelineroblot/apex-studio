import clsx from "clsx";
import Link from "next/link";
import type { UploadItem } from "@/lib/upload/db";
import { formatBytes } from "@/lib/format";
import { Button } from "@/components/ui/Button";

const STATUS_LABEL: Record<UploadItem["status"], string> = {
  pending: "En attente",
  uploading: "Envoi…",
  done: "Envoyé",
  error: "Échec",
  rejected: "Refusé — en quarantaine",
};

const STATUS_CLASSES: Record<UploadItem["status"], string> = {
  pending: "text-ink-400",
  uploading: "text-accent-600",
  done: "text-ok-600",
  error: "text-danger-600",
  rejected: "text-danger-600",
};

export function UploadQueueList({
  items,
  onRetry,
}: {
  items: UploadItem[];
  onRetry: (id: string) => void;
}) {
  return (
    <ul className="max-h-96 divide-y divide-ink-50 overflow-y-auto rounded-lg border border-ink-100 bg-white">
      {items.map((item) => (
        <li key={item.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-ink-800">{item.name}</p>
            <p className="text-xs text-ink-400">
              {formatBytes(item.size)}
              {item.error && (item.status === "error" || item.status === "rejected")
                ? ` — ${item.error}`
                : null}
            </p>
          </div>
          <span className={clsx("shrink-0 text-xs font-medium", STATUS_CLASSES[item.status])}>
            {STATUS_LABEL[item.status]}
          </span>
          {item.status === "error" ? (
            <Button size="sm" variant="secondary" onClick={() => onRetry(item.id)}>
              Réessayer
            </Button>
          ) : null}
          {item.status === "rejected" && item.mediaId != null ? (
            <Link
              href={`/media/${item.mediaId}`}
              className="shrink-0 text-xs font-medium text-accent-600 hover:underline"
            >
              Voir en quarantaine
            </Link>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
