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
