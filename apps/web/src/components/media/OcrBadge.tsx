import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { formatPercent } from "@/lib/format";

/**
 * Score de confiance OCR — couleur alignée sur les seuils **courants** (§ tâche 1 : « affiche
 * la photo, le numéro lu, le score de confiance »). Formule documentée au survol
 * (`title`, § §3-J.3 du plan) : le prospect doit comprendre ce qu'il regarde, pas seulement
 * le constater.
 */
export function OcrBadge({
  confidence,
  thresholds,
}: {
  confidence: number;
  thresholds: { high: number; low: number };
}) {
  const tone: BadgeTone = confidence >= thresholds.high ? "ok" : confidence >= thresholds.low ? "warn" : "danger";
  return (
    <span
      title={
        "Score = confiance de lecture × pénalité géométrique × pénalité de longueur, borné à [0, 1]. " +
        `Seuil haut courant : ${formatPercent(thresholds.high)} · seuil bas courant : ${formatPercent(thresholds.low)}.`
      }
    >
      <Badge tone={tone}>Confiance {formatPercent(confidence)}</Badge>
    </span>
  );
}
