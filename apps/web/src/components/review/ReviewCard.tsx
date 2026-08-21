import type { ReviewItem } from "@/lib/api/types";
import type { StagedDecision } from "@/lib/review/batch";
import { AuthImage } from "@/components/media/AuthImage";
import { OcrBadge } from "@/components/media/OcrBadge";
import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";

/**
 * Boîte OCR surlignée sur l'aperçu grand format (§ tâche 1). `bbox` est désormais le vrai
 * schéma fermé du contrat (`OcrBoundingBox`, `apex.schemas.review`) : `x/y/w/h`
 * **normalisés `[0..1]`**, fraction de l'image, indépendants de la résolution d'affichage
 * — confirmé par la docstring de module côté backend. `quad`/`image_width`/
 * `image_height` existent aussi sur le contrat mais ne sont pas encore consommés ici (pas
 * de rendu incliné prévu au plan).
 */
function readBbox(bbox: ReviewItem["bbox"] | null | undefined): { x: number; y: number; width: number; height: number } | null {
  if (!bbox) return null;
  const { x, y, w, h } = bbox;
  if (typeof x === "number" && typeof y === "number" && typeof w === "number" && typeof h === "number") {
    return { x, y, width: w, height: h };
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
  // `resolution` porte désormais explicitement la distinction « pas sûr » (`review`, score
  // entre les seuils, engagement toujours suggéré) vs « sûr mais incohérent »
  // (`not_engaged`, numéro absent des engagements) — § passe d'intégration live J2.
  // Auparavant déduite de `item.suggested_engagement == null`, une corrélation qui tenait
  // par construction de `classify.decide()` côté backend mais que rien ne garantissait
  // côté contrat. `GET /review/queue` ne renvoie en pratique que des candidats `review`
  // (les `not_engaged` vivent dans le bac « incohérences » de la recherche à facettes),
  // mais `ReviewCard` reste correct si ça change un jour.
  const isInconsistent = item.resolution === "not_engaged";

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

        {!isInconsistent && item.suggested_engagement ? (
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
