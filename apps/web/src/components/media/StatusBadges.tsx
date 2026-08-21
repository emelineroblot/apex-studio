import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { ATTACHMENT_STATUS_LABELS, INGEST_STATUS_LABELS, quarantineReasonLabel } from "@/lib/labels";
import type { AttachmentStatus, IngestStatus } from "@/lib/api/types";

const INGEST_TONE: Record<IngestStatus, BadgeTone> = {
  uploaded: "neutral",
  processing: "accent",
  ingested: "ok",
  quarantined: "danger",
};

const ATTACHMENT_TONE: Record<AttachmentStatus, BadgeTone> = {
  unattached: "warn",
  shooting_attached: "ok",
  engagement_attached: "ok",
  pending_review: "accent",
  inconsistent: "danger",
};

export function IngestStatusBadge({ status }: { status: IngestStatus }) {
  return <Badge tone={INGEST_TONE[status]}>{INGEST_STATUS_LABELS[status]}</Badge>;
}

export function AttachmentStatusBadge({ status }: { status: AttachmentStatus }) {
  return <Badge tone={ATTACHMENT_TONE[status]}>{ATTACHMENT_STATUS_LABELS[status]}</Badge>;
}

export function QuarantineReasonBadge({ reason }: { reason: string | null }) {
  return (
    <Badge tone="danger" className="max-w-full whitespace-normal text-left">
      {quarantineReasonLabel(reason)}
    </Badge>
  );
}

/**
 * `media.is_simulated` (§3-N.1 du plan) — « on ne fait pas passer un jeu généré pour du
 * traitement réel, c'est un argument de crédibilité, pas un aveu ». Revue J2 🟠1 : le champ
 * traversait toute la pile sans jamais être lu par un composant de rendu. N'affiche rien
 * pour un média réel (`false`) — le badge n'existe que pour marquer l'exception.
 */
export function SimulatedBadge({ className }: { className?: string }) {
  return (
    <span title="Média généré pour peupler le jeu de démonstration — pas un traitement réel du pipeline.">
      <Badge tone="accent" className={className}>
        Simulé
      </Badge>
    </span>
  );
}
