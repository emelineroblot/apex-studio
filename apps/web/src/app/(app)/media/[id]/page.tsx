"use client";

import { use, useState } from "react";
import Link from "next/link";
import * as mediaApi from "@/lib/api/resources/media";
import * as shootingsApi from "@/lib/api/resources/shootings";
import * as reviewApi from "@/lib/api/resources/review";
import * as settingsApi from "@/lib/api/resources/settings";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatBytes, formatDateTime } from "@/lib/format";
import { AttachmentStatusBadge, IngestStatusBadge } from "@/components/media/StatusBadges";
import { OcrBadge } from "@/components/media/OcrBadge";
import { OCR_RESOLUTION_LABELS } from "@/lib/labels";
import { AuthImage } from "@/components/media/AuthImage";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ErrorState, Spinner } from "@/components/ui/States";
import { inputClassName } from "@/components/ui/Field";
import { quarantineReasonLabel, unattachedReasonLabel } from "@/lib/labels";
import { seriesUrl } from "@/components/media/MediaGrid";

export default function MediaDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const mediaId = Number(id);

  const { data: media, loading, error, reload } = useAsync(() => mediaApi.get(mediaId), [mediaId]);
  const { data: shootingsPage } = useAsync(() => shootingsApi.list({ limit: 100 }), []);
  const { data: ocr } = useAsync(() => reviewApi.ocrCandidates(mediaId), [mediaId]);
  const { data: ocrSettings } = useAsync(() => settingsApi.getOcr(), []);
  const [attachTarget, setAttachTarget] = useState("");
  const [attaching, setAttaching] = useState(false);
  const [attachError, setAttachError] = useState<string | null>(null);

  async function handleAttach() {
    if (!attachTarget) return;
    setAttaching(true);
    setAttachError(null);
    try {
      await mediaApi.attach(mediaId, Number(attachTarget));
      reload();
    } catch (err) {
      setAttachError(friendlyErrorMessage(err));
    } finally {
      setAttaching(false);
    }
  }

  return (
    <div>
      <Link href="/library" className="text-sm text-ink-500 hover:text-accent-600">
        ← Retour à la bibliothèque
      </Link>

      {loading ? <Spinner label="Chargement du média…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {media ? (
        <>
          <PageHeader
            title={media.original_filename}
            description={`Média #${media.id} · ${formatBytes(media.byte_size)}`}
            actions={
              <>
                <IngestStatusBadge status={media.ingest_status} />
                <AttachmentStatusBadge status={media.attachment_status} />
              </>
            }
          />

          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <div className="flex flex-col gap-4">
              <Card className="overflow-hidden p-0">
                <div className="aspect-[3/2] w-full bg-ink-900">
                  <AuthImage
                    src={mediaApi.previewUrl(media.id)}
                    alt={`Aperçu filigrané de ${media.original_filename}`}
                    className="h-full w-full object-contain"
                  />
                </div>
              </Card>

              {media.ingest_status === "quarantined" ? (
                <Notice tone="danger">
                  En quarantaine — {quarantineReasonLabel(media.quarantine_reason)}.
                </Notice>
              ) : null}

              {media.attachment_status === "unattached" ? (
                <Card>
                  <h2 className="mb-1 text-sm font-semibold text-ink-900">Bac « à rattacher »</h2>
                  <p className="mb-3 text-sm text-ink-600">{unattachedReasonLabel(media.attachment_detail)}</p>
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="flex flex-col gap-1.5 text-sm">
                      <span className="font-medium text-ink-800">Rattacher manuellement au shooting</span>
                      <select
                        value={attachTarget}
                        onChange={(e) => setAttachTarget(e.target.value)}
                        className={inputClassName("min-w-[220px]")}
                      >
                        <option value="">Choisir un shooting</option>
                        {(shootingsPage?.items ?? []).map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.title}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Button loading={attaching} disabled={!attachTarget} onClick={handleAttach}>
                      Rattacher
                    </Button>
                  </div>
                  {attachError ? (
                    <div className="mt-3">
                      <Notice tone="danger">{attachError}</Notice>
                    </div>
                  ) : null}
                </Card>
              ) : null}

              {ocr && ocr.candidates.length > 0 ? (
                <Card>
                  <h2 className="mb-3 text-sm font-semibold text-ink-900">Lectures OCR (§ J2)</h2>
                  <ul className="flex flex-col gap-2">
                    {ocr.candidates.map((c) => (
                      <li key={c.id} className="flex flex-wrap items-center gap-2 text-sm text-ink-700">
                        <span className="font-mono">{c.raw_text}</span>
                        {c.normalized_number ? <span>→ n°{c.normalized_number}</span> : null}
                        <OcrBadge confidence={c.confidence} thresholds={{ high: ocrSettings?.high ?? 0.8, low: ocrSettings?.low ?? 0.45 }} />
                        <span className="text-xs text-ink-400">{OCR_RESOLUTION_LABELS[c.resolution]}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : null}

              <Card>
                <h2 className="mb-3 text-sm font-semibold text-ink-900">Journal du pipeline</h2>
                {media.events.length === 0 ? (
                  <p className="text-sm text-ink-500">Aucune étape enregistrée.</p>
                ) : (
                  <ol className="flex flex-wrap gap-2 text-xs">
                    {media.events.map((step, i) => (
                      <li key={i} className="rounded-full bg-ink-100 px-2.5 py-1 text-ink-700">
                        {i + 1}. {step}
                      </li>
                    ))}
                  </ol>
                )}
              </Card>
            </div>

            <div className="flex flex-col gap-4">
              <Card>
                <h2 className="mb-3 text-sm font-semibold text-ink-900">EXIF</h2>
                <dl className="flex flex-col gap-1.5 text-sm">
                  <ExifRow label="Pris le" value={formatDateTime(media.shot_at)} />
                  <ExifRow label="Horodatage brut (EXIF)" value={media.shot_at_exif ?? "—"} />
                  <ExifRow label="Objectif" value={media.exif.lens_model ?? "—"} />
                  <ExifRow label="ISO" value={media.exif.iso != null ? String(media.exif.iso) : "—"} />
                  <ExifRow label="Vitesse" value={media.exif.shutter_speed_label ?? "—"} />
                  <ExifRow label="Ouverture" value={media.exif.aperture != null ? `f/${media.exif.aperture}` : "—"} />
                  <ExifRow label="Focale" value={media.exif.focal_length != null ? `${media.exif.focal_length} mm` : "—"} />
                  <ExifRow label="Dimensions" value={media.width && media.height ? `${media.width} × ${media.height} px` : "—"} />
                </dl>
              </Card>

              <Card>
                <h2 className="mb-3 text-sm font-semibold text-ink-900">Série &amp; doublon</h2>
                <dl className="flex flex-col gap-1.5 text-sm">
                  <ExifRow
                    label="Rafale"
                    value={
                      media.series_id ? (
                        <span className="inline-flex items-center gap-2">
                          {`Série #${media.series_id}${media.is_series_representative ? " (représentant)" : ""}`}
                          <Link
                            href={seriesUrl(media.series_id, media.shooting_id)}
                            className="text-accent-600 hover:underline"
                          >
                            Voir toute la série
                          </Link>
                        </span>
                      ) : (
                        "Isolé"
                      )
                    }
                  />
                  <ExifRow
                    label="Doublon"
                    value={
                      media.duplicate_of_media_id ? (
                        <Link href={`/media/${media.duplicate_of_media_id}`} className="text-accent-600 hover:underline">
                          Doublon de #{media.duplicate_of_media_id}
                        </Link>
                      ) : (
                        "Non"
                      )
                    }
                  />
                </dl>
              </Card>

              <Card>
                <h2 className="mb-3 text-sm font-semibold text-ink-900">Rattachement</h2>
                <dl className="flex flex-col gap-1.5 text-sm">
                  <ExifRow
                    label="Shooting"
                    value={
                      media.shooting_id ? (
                        <Link href={`/shootings/${media.shooting_id}`} className="text-accent-600 hover:underline">
                          Voir le shooting #{media.shooting_id}
                        </Link>
                      ) : (
                        "Aucun"
                      )
                    }
                  />
                  <ExifRow label="Source" value={media.attachment_source ?? "—"} />
                </dl>
                {media.engagements.length > 0 ? (
                  <div className="mt-3">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wide text-ink-400">Engagements</p>
                    <ul className="flex flex-wrap gap-1.5">
                      {media.engagements.map((eng) => (
                        <li key={eng.engagement_id} className="rounded-full bg-accent-100 px-2.5 py-1 text-xs text-accent-700">
                          N° {eng.car_number}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function ExifRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-500">{label}</dt>
      <dd className="text-right font-medium text-ink-800">{value}</dd>
    </div>
  );
}
