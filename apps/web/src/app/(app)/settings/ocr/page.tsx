"use client";

import { useState } from "react";
import * as settingsApi from "@/lib/api/resources/settings";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { OCR_RESOLUTION_LABELS } from "@/lib/labels";
import { formatDateTime, formatPercent } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ErrorState, Spinner } from "@/components/ui/States";
import type { OcrDistribution, OcrPreviewDistribution } from "@/lib/api/types";

const BUCKET_TONE: Record<keyof OcrDistribution, string> = {
  auto: "bg-ok-500",
  review: "bg-warn-500",
  abstain: "bg-ink-300",
  not_engaged: "bg-danger-500",
};

/**
 * Composant générique — accepte aussi bien `OcrDistribution` (4 cases, § « répartition
 * actuelle ») que `OcrPreviewDistribution` (3 cases, § aperçu synchrone) : `not_engaged`
 * absent de l'aperçu n'est jamais rendu (il ne bouge pas avec les seuils, § `lib/ocr/
 * reclassify.ts`), sans dupliquer le composant pour autant.
 */
const FULL_KEYS: (keyof OcrDistribution)[] = ["auto", "review", "abstain", "not_engaged"];
const PREVIEW_KEYS: (keyof OcrDistribution)[] = ["auto", "review", "abstain"];

function DistributionBars({
  distribution,
  title,
}: {
  distribution: OcrDistribution | OcrPreviewDistribution;
  title: string;
}) {
  const keys = "not_engaged" in distribution ? FULL_KEYS : PREVIEW_KEYS;
  const values: Record<keyof OcrDistribution, number> = {
    auto: distribution.auto,
    review: distribution.review,
    abstain: distribution.abstain,
    not_engaged: "not_engaged" in distribution ? distribution.not_engaged : 0,
  };
  const total = keys.reduce((sum, key) => sum + values[key], 0);
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">{title}</p>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-ink-100">
        {keys.map((key) => (
          <div
            key={key}
            className={BUCKET_TONE[key]}
            style={{ width: total > 0 ? `${(values[key] / total) * 100}%` : 0 }}
            title={`${OCR_RESOLUTION_LABELS[key]} : ${values[key]}`}
          />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-600">
        {keys.map((key) => (
          <li key={key} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${BUCKET_TONE[key]}`} aria-hidden="true" />
            {OCR_RESOLUTION_LABELS[key]} — <span className="font-medium">{values[key]}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function OcrSettingsPage() {
  const { data: settings, loading, error, reload } = useAsync(() => settingsApi.getOcr(), []);
  const [high, setHigh] = useState<number | null>(null);
  const [low, setLow] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<{ preview: OcrPreviewDistribution; updatedAt: string } | null>(null);

  const effectiveHigh = high ?? settings?.high ?? 0.8;
  const effectiveLow = low ?? settings?.low ?? 0.45;
  const changed = settings != null && (effectiveHigh !== settings.high || effectiveLow !== settings.low);
  const invalid = effectiveLow >= effectiveHigh;

  async function apply() {
    if (invalid) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await settingsApi.updateOcr({ high: effectiveHigh, low: effectiveLow });
      setResult({ preview: response.preview_distribution, updatedAt: response.settings.updated_at });
      reload();
    } catch (err) {
      setSubmitError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Réglage des seuils OCR"
        description="Deux seuils configurables, sans redéploiement — réservé au rôle dirigeant."
      />

      {loading ? <Spinner label="Chargement des réglages…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && settings ? (
        <div className="flex flex-col gap-5">
          <Notice tone="accent">
            Les candidats OCR bruts sont déjà persistés (texte lu, score, boîte). Changer un seuil{" "}
            <strong>redistribue instantanément les cas déjà calculés</strong> entre rattachement automatique,
            file de validation et abstention — aucune photo n&apos;est relue, aucun traitement long n&apos;est
            relancé.
          </Notice>

          <Card>
            <div className="flex flex-col gap-5">
              <div>
                <label htmlFor="ocr-high" className="mb-1 flex justify-between text-sm font-medium text-ink-800">
                  <span>Seuil haut — rattachement automatique</span>
                  <span className="tabular-nums text-accent-700">{formatPercent(effectiveHigh)}</span>
                </label>
                <input
                  id="ocr-high"
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={effectiveHigh}
                  onChange={(e) => setHigh(Number(e.target.value))}
                  className="w-full accent-accent-600"
                />
                <p className="text-xs text-ink-500">Au-dessus de ce score, le numéro lu est rattaché sans intervention humaine.</p>
              </div>

              <div>
                <label htmlFor="ocr-low" className="mb-1 flex justify-between text-sm font-medium text-ink-800">
                  <span>Seuil bas — abstention</span>
                  <span className="tabular-nums text-accent-700">{formatPercent(effectiveLow)}</span>
                </label>
                <input
                  id="ocr-low"
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={effectiveLow}
                  onChange={(e) => setLow(Number(e.target.value))}
                  className="w-full accent-accent-600"
                />
                <p className="text-xs text-ink-500">
                  En dessous de ce score, la lecture est trop incertaine — le média reste rattaché au shooting sans
                  engagement.
                </p>
              </div>

              {invalid ? <Notice tone="danger">Le seuil bas doit rester strictement inférieur au seuil haut.</Notice> : null}

              <div className="flex items-center gap-3">
                <Button disabled={!changed || invalid} loading={submitting} onClick={apply}>
                  Appliquer les nouveaux seuils
                </Button>
                {changed ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setHigh(null);
                      setLow(null);
                    }}
                  >
                    Annuler la modification
                  </Button>
                ) : null}
              </div>
            </div>
          </Card>

          {submitError ? <Notice tone="danger">{submitError}</Notice> : null}

          <Card>
            <DistributionBars distribution={settings.distribution} title="Répartition actuelle" />
            <p className="mt-2 text-xs text-ink-400">
              Seuils en vigueur depuis le {formatDateTime(settings.updated_at)} · moteur {settings.engine_version}.
            </p>
          </Card>

          {result ? (
            <Card className="border-ok-100 bg-ok-100/30">
              <DistributionBars distribution={result.preview} title="Aperçu de la redistribution — calculé sans relire aucune image" />
              <p className="mt-2 text-xs text-ink-500">
                Seuils enregistrés le {formatDateTime(result.updatedAt)}. Les candidats bruts sont re-projetés par
                la file de tâches ; « répartition actuelle » ci-dessus se met à jour dès que le job a tourné —
                quelques secondes, sur des candidats déjà calculés.
              </p>
            </Card>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
