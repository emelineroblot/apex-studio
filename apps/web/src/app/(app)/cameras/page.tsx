"use client";

import { useState } from "react";
import * as camerasApi from "@/lib/api/resources/cameras";
import * as mediaApi from "@/lib/api/resources/media";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { Field, inputClassName } from "@/components/ui/Field";
import type { CameraOut } from "@/lib/api/types";

export default function CamerasPage() {
  const { data: cameras, loading, error, reload } = useAsync(() => camerasApi.list(), []);

  return (
    <div>
      <PageHeader
        title="Boîtiers"
        description="Décalage d'horloge par appareil — corrige rétroactivement le rattachement de ses photos."
      />

      {loading ? <Spinner label="Chargement des boîtiers…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error ? (
        !cameras || cameras.length === 0 ? (
          <EmptyState title="Aucun boîtier enregistré" description="Les boîtiers apparaissent après un premier dépôt de photos." />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {cameras.map((camera) => (
              <CameraCard key={camera.id} camera={camera} onUpdated={reload} />
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

function CameraCard({ camera, onUpdated }: { camera: CameraOut; onUpdated: () => void }) {
  const [offset, setOffset] = useState(String(camera.clock_offset_seconds));
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const changed = Number(offset) !== camera.clock_offset_seconds;

  async function applyChange() {
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const before = await mediaApi.list({ unattached: true, limit: 1 });
      await camerasApi.update(camera.id, { clock_offset_seconds: Number(offset) });
      const after = await mediaApi.list({ unattached: true, limit: 1 });
      const beforeCount = before.total ?? before.items.length;
      const afterCount = after.total ?? after.items.length;
      const reattached = Math.max(0, beforeCount - afterCount);
      setResult(
        reattached > 0
          ? `${reattached} photo(s) re-rattachée(s) suite à ce réglage.`
          : "Réglage enregistré — aucune photo du bac « à rattacher » n'était concernée.",
      );
      setConfirming(false);
      onUpdated();
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold text-ink-900">
        {camera.make} {camera.model}
      </h2>
      <p className="text-xs text-ink-500">N° de série {camera.exif_serial ?? "inconnu"}</p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <Field label="Décalage d'horloge (secondes)" hint="Négatif si l'horloge du boîtier retardait.">
          {(p) => (
            <input
              {...p}
              type="number"
              value={offset}
              onChange={(e) => {
                setOffset(e.target.value);
                setResult(null);
              }}
              className={inputClassName("w-40")}
            />
          )}
        </Field>
        <Button disabled={!changed} onClick={() => setConfirming(true)}>
          Appliquer
        </Button>
      </div>

      {confirming ? (
        <div className="mt-3">
          <Notice tone="warn">
            <p className="mb-2">
              Cette modification va <strong>re-déclencher le rattachement</strong> de toutes les photos non
              rattachées de ce boîtier, en recalculant leur horodatage. Confirmer ?
            </p>
            <div className="flex gap-2">
              <Button size="sm" loading={submitting} onClick={applyChange}>
                Confirmer
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setConfirming(false)}>
                Annuler
              </Button>
            </div>
          </Notice>
        </div>
      ) : null}

      {result ? (
        <div className="mt-3">
          <Notice tone="ok">{result}</Notice>
        </div>
      ) : null}
      {error ? (
        <div className="mt-3">
          <Notice tone="danger">{error}</Notice>
        </div>
      ) : null}
    </Card>
  );
}
