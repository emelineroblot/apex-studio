import type { ReviewItem } from "@/lib/api/types";
import type { StagedDecision } from "@/lib/review/batch";
import { AuthImage } from "@/components/media/AuthImage";
import { OcrBadge } from "@/components/media/OcrBadge";
import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";

/**
 * Boîte OCR surlignée sur l'aperçu grand format (§ tâche 1). `bbox` n'est pas fermé par le
 * contrat (`OcrCandidateOut.bbox: additionalProperties: true`) — hypothèse frontend
 * documentée dans `implementation.md` : coordonnées **normalisées `[0..1]`**
 * `{x, y, width, height}`, relatives à l'aperçu affiché. À confirmer avec le backend quand
 * `pipeline/ocr/engine.py` sera branché.
 */
function readBbox(bbox: unknown): { x: number; y: number; width: number; height: number } | null {
  if (!bbox || typeof bbox !== "object") return null;
  const b = bbox as Record<string, unknown>;
  const { x, y, width, height } = b;
  if (typeof x === "number" && typeof y === "number" && typeof width === "number" && typeof height === "number") {
    return { x, y, width, height };
  }
  return null;
}

export function ReviewCard({
  item,
  thresholds,
  decision,
  selected,
  onNumberShortcut,
}: {
  item: ReviewItem;
  thresholds: { high: number; low: number };
  decision: StagedDecision | undefined;
  selected: boolean;
  /** Callback souris pour les suggestions numérotées 1-9 (même effet que le raccourci clavier). */
  onNumberShortcut: (engagementId: number) => void;
}) {
  const box = readBbox(item.bbox);
  const isInconsistent = item.suggested_engagement == null;

  return (
    <div
      className={`overflow-hidden rounded-xl border-2 bg-white ${
        selected ? "border-accent-600" : decision ? decisionBorder(decision.action) : "border-ink-100"
      }`}
    >
      <div className="relative aspect-[3/2] w-full bg-ink-950">
        <AuthImage src={item.media.preview_url} alt={`Aperçu du média #${item.media.id}`} className="h-full w-full object-contain" />
        {box ? (
          <div
            className="absolute rounded border-2 border-warn-500 shadow-[0_0_0_9999px_rgba(0,0,0,0.15)]"
            style={{
              left: `${box.x * 100}%`,
              top: `${box.y * 100}%`,
              width: `${box.width * 100}%`,
              height: `${box.height * 100}%`,
            }}
            aria-hidden="true"
          />
        ) : null}
        {decision ? (
          <span className="absolute right-2 top-2 rounded bg-ink-950/85 px-2 py-1 text-xs font-medium text-white">
            {decisionLabel(decision.action)}
          </span>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <OcrBadge confidence={item.confidence} thresholds={thresholds} />
          {isInconsistent ? (
            <Badge tone="danger">Incohérence — numéro non reconnu</Badge>
          ) : (
            <Badge tone="warn">À confirmer</Badge>
          )}
          <span className="text-xs text-ink-400">{item.media.shot_at ? formatDateTime(item.media.shot_at) : "Horodatage inconnu"}</span>
        </div>

        <div className="text-sm text-ink-700">
          <p>
            Texte lu : <span className="font-mono font-semibold">{item.raw_text}</span>
            {item.normalized_number ? (
              <>
                {" "}
                → numéro normalisé <span className="font-mono font-semibold">{item.normalized_number}</span>
              </>
            ) : null}
          </p>
        </div>

        {item.suggested_engagement ? (
          <div className="rounded-lg border border-accent-100 bg-accent-50 p-3 text-sm">
            <p className="font-medium text-accent-800">
              Engagement suggéré — n°{item.suggested_engagement.car_number}
            </p>
            <p className="text-accent-700">
              {[item.suggested_engagement.driver, item.suggested_engagement.team, item.suggested_engagement.client]
                .filter(Boolean)
                .join(" · ") || "Détails indisponibles"}
            </p>
          </div>
        ) : (
          <p className="rounded-lg border border-danger-100 bg-danger-100/40 p-3 text-sm text-danger-700">
            Ce numéro n&apos;existe dans aucun engagement de ce shooting — impossible de rattacher
            automatiquement. Choisissez une correspondance ci-dessous ou rejetez la lecture.
          </p>
        )}

        {item.other_engagements.length > 0 ? (
          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-500">
              Rattacher à un autre engagement
            </p>
            <ul className="flex flex-wrap gap-1.5">
              {item.other_engagements.map((eng, idx) => (
                <li key={eng.id}>
                  <button
                    type="button"
                    onClick={() => onNumberShortcut(eng.id)}
                    className="flex items-center gap-1.5 rounded-full border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-700 hover:border-accent-600 hover:text-accent-700 focus-visible:outline-2 focus-visible:outline-accent-600"
                  >
                    <kbd className="rounded bg-ink-100 px-1 font-mono text-[10px]">{idx + 1}</kbd>
                    n°{eng.car_number}
                    {eng.driver ? ` — ${eng.driver}` : ""}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function decisionBorder(action: StagedDecision["action"]): string {
  if (action === "accept") return "border-ok-500";
  if (action === "reject") return "border-danger-500";
  return "border-accent-500";
}

function decisionLabel(action: StagedDecision["action"]): string {
  if (action === "accept") return "Acceptée (en attente d'envoi)";
  if (action === "reject") return "Rejetée (en attente d'envoi)";
  return "Réassignée (en attente d'envoi)";
}
