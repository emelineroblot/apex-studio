"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import * as batchesApi from "@/lib/api/resources/batches";
import type { BatchStatusResponse } from "@/lib/api/types";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { ErrorState, Spinner } from "@/components/ui/States";
import { Notice } from "@/components/ui/Notice";

const POLL_MS = 1000;

export default function BatchStatusPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const batchId = Number(id);

  const [status, setStatus] = useState<BatchStatusResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const result = await batchesApi.getStatus(batchId);
        if (cancelled) return;
        setStatus(result);
        setError(null);
        setLoading(false);
        if (!result.done) {
          timer = setTimeout(poll, POLL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err);
        setLoading(false);
        timer = setTimeout(poll, POLL_MS * 3);
      }
    }
    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [batchId]);

  return (
    <div>
      <Link href="/upload" className="text-sm text-ink-500 hover:text-accent-600">
        ← Retour au dépôt
      </Link>

      <PageHeader
        title={`Lot #${batchId}`}
        description="Suivi du traitement — mis à jour toutes les secondes."
        actions={status ? <Badge tone={status.done ? "ok" : "accent"}>{status.done ? "Terminé" : "En cours"}</Badge> : undefined}
      />

      {loading && !status ? <Spinner label="Chargement du lot…" /> : null}
      {error && !status ? <ErrorState message={friendlyErrorMessage(error)} /> : null}

      {status ? (
        <div className="flex flex-col gap-4">
          <Card>
            <ProgressBar
              value={status.progress}
              label={`${status.counts.ingested + status.counts.quarantined} / ${status.expected_count} traités`}
            />
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Déposés" value={status.received_count} />
              <Stat label="En traitement" value={status.counts.processing} />
              <Stat label="Ingérés" value={status.counts.ingested} />
              <Stat label="En quarantaine" value={status.counts.quarantined} />
              <Stat label="Rattachés" value={status.attached_count} />
              <Stat label="Doublons" value={status.duplicate_count} />
            </div>
          </Card>

          {status.missing_count > 0 ? (
            <Notice tone="warn">
              {status.missing_count} fichier(s) annoncé(s) à l&apos;ouverture du lot n&apos;ont jamais été reçus par
              le serveur — vérifiez la connexion et reprenez l&apos;envoi si besoin.
            </Notice>
          ) : null}

          <Card>
            <h2 className="mb-3 text-sm font-semibold text-ink-900">Journal d&apos;ingestion</h2>
            {status.events.length === 0 ? (
              <p className="text-sm text-ink-500">Aucun événement pour l&apos;instant.</p>
            ) : (
              <ul className="flex flex-col gap-1.5 text-sm">
                {status.events.map((ev, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 border-b border-ink-50 pb-1.5 last:border-0">
                    <span className="text-ink-700">
                      <span className="font-medium">{ev.step}</span> — {ev.message ?? ev.status}
                    </span>
                    <span className="shrink-0 text-xs text-ink-400">{formatDateTime(ev.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {status.done ? (
            <Notice tone="ok">
              Traitement terminé. <Link href="/library" className="underline">Voir la bibliothèque</Link>.
            </Notice>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-ink-50 px-3 py-2">
      <p className="text-lg font-semibold text-ink-900">{value}</p>
      <p className="text-xs text-ink-500">{label}</p>
    </div>
  );
}
