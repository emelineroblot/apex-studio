"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import * as shootingsApi from "@/lib/api/resources/shootings";
import { useAsync } from "@/hooks/useAsync";
import { useUploadQueue } from "@/lib/upload/useUploadQueue";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Spinner } from "@/components/ui/States";
import { inputClassName } from "@/components/ui/Field";
import { Dropzone } from "@/components/upload/Dropzone";
import { UploadQueueList } from "@/components/upload/UploadQueueList";

export default function UploadPage() {
  const router = useRouter();
  const { data: shootingsPage } = useAsync(() => shootingsApi.list({ limit: 100 }), []);
  const [shootingHintId, setShootingHintId] = useState("");
  const [startError, setStartError] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);

  const queue = useUploadQueue();

  async function handleFirstDrop(files: File[]) {
    setStartError(null);
    try {
      await queue.startBatch(files, shootingHintId ? Number(shootingHintId) : null);
    } catch (err) {
      setStartError(friendlyErrorMessage(err));
    }
  }

  async function handleClose() {
    setClosing(true);
    try {
      await queue.closeBatch();
      if (queue.meta) router.push(`/batches/${queue.meta.batchId}`);
    } catch (err) {
      setStartError(friendlyErrorMessage(err));
    } finally {
      setClosing(false);
    }
  }

  if (!queue.hydrated) {
    return <Spinner label="Préparation de la file d'envoi…" />;
  }

  const hasActiveBatch = queue.meta && !queue.meta.closed;
  const allDone = queue.total > 0 && queue.doneCount === queue.total;
  const hasPendingWork = queue.pendingOrUploadingCount > 0;

  return (
    <div>
      <PageHeader
        title="Dépôt de photos"
        description="Glissez-déposez un lot — l'envoi se poursuit en tâche de fond, avec reprise après interruption."
      />

      {!hasActiveBatch ? (
        <Card className="mb-6">
          <label className="mb-4 flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink-800">Shooting pressenti (facultatif)</span>
            <select
              value={shootingHintId}
              onChange={(e) => setShootingHintId(e.target.value)}
              className={inputClassName("max-w-sm")}
            >
              <option value="">Laisser le pipeline déterminer le shooting</option>
              {(shootingsPage?.items ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
            <span className="text-xs text-ink-500">
              Le rattachement définitif se fait par horodatage EXIF, ceci n&apos;est qu&apos;une indication.
            </span>
          </label>
          <Dropzone onFiles={handleFirstDrop} />
        </Card>
      ) : null}

      {startError ? (
        <div className="mb-4">
          <Notice tone="danger">{startError}</Notice>
        </div>
      ) : null}

      {queue.total > 0 ? (
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex-1 min-w-[240px]">
              <ProgressBar
                value={queue.total ? queue.doneCount / queue.total : 0}
                label={`${queue.doneCount} / ${queue.total} fichiers envoyés`}
              />
            </div>
            <div className="flex items-center gap-2">
              {!queue.running && hasPendingWork ? (
                <Button variant="secondary" onClick={queue.resume}>
                  Reprendre l&apos;envoi
                </Button>
              ) : null}
              {queue.running ? <Spinner label="Envoi en cours…" /> : null}
            </div>
          </div>

          {hasActiveBatch && queue.total > 0 && !hasPendingWork && !queue.running ? (
            <div className="mb-4">
              <Notice tone={queue.errorCount > 0 || queue.rejectedCount > 0 ? "warn" : "ok"}>
                {[
                  queue.errorCount > 0
                    ? `${queue.errorCount} fichier(s) en échec après plusieurs tentatives — corrigez-les ou continuez sans eux.`
                    : null,
                  queue.rejectedCount > 0
                    ? `${queue.rejectedCount} fichier(s) refusé(s) (quota dépassé ou taille excessive) — déjà en quarantaine, aucune reprise possible depuis cet écran.`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" ") || "Tous les fichiers ont été envoyés."}
              </Notice>
            </div>
          ) : null}

          <UploadQueueList items={queue.items} onRetry={queue.retryItem} />

          <div className="mt-4 flex flex-wrap gap-2">
            {hasActiveBatch ? (
              <Dropzone
                onFiles={queue.addFiles}
                label="Ajouter d'autres fichiers à ce lot"
              />
            ) : null}
          </div>

          {hasActiveBatch ? (
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => void queue.abandon()}>
                Abandonner le lot
              </Button>
              <Button loading={closing} disabled={!allDone && queue.errorCount === 0 && hasPendingWork} onClick={handleClose}>
                Clore le lot et suivre le traitement
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}
