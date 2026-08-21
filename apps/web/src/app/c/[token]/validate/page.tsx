"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as publicApi from "@/lib/api/resources/publicSpace";
import { ApiError } from "@/lib/api/errors";
import type { PublicDeliveryStatusResponse, PublicSelectionResponse } from "@/lib/api/types";
import { useClientSession, handleClientApiError } from "@/lib/client/useClientSession";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { ErrorState, Spinner } from "@/components/ui/States";

/** Cadence du suivi de préparation. Deux secondes : assez réactif pour que l'attente
 * paraisse suivie, assez espacé pour ne pas marteler une fonction serverless. */
const POLL_INTERVAL_MS = 2000;

function formatSize(bytes: number | null): string {
  if (bytes === null) return "—";
  const mb = bytes / 1_000_000;
  return mb >= 1000 ? `${(mb / 1000).toFixed(1)} Go` : `${Math.round(mb)} Mo`;
}

/**
 * Récapitulatif, validation, puis suivi de la préparation jusqu'au téléchargement.
 *
 * Un seul écran pour les trois moments, parce que c'est un seul geste du point de vue du
 * client : il confirme, il attend, il récupère. Le point important est l'avertissement
 * d'irréversibilité **avant** le clic — après, la sélection est figée et alimente la
 * facture.
 */
export default function ClientValidatePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const router = useRouter();
  const { session, collection, loading: sessionLoading, error: sessionError } = useClientSession(token);
  const accessToken = session?.accessToken ?? null;

  const [selection, setSelection] = useState<PublicSelectionResponse | null>(null);
  const [delivery, setDelivery] = useState<PublicDeliveryStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [nextSelection, nextDelivery] = await Promise.all([
        publicApi.getSelection(accessToken),
        publicApi.getDelivery(accessToken),
      ]);
      setSelection(nextSelection);
      setDelivery(nextDelivery);
      setFailure(null);
    } catch (err) {
      if (handleClientApiError(err, token, router)) return;
      setFailure("Nous n'arrivons pas à afficher l'état de votre commande.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, token, router]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Suivi de préparation : on ne sonde que tant qu'il y a quelque chose à attendre.
  useEffect(() => {
    const inProgress =
      selection?.status === "validated" &&
      delivery !== null &&
      (delivery.status === "pending" || delivery.status === "building");
    if (!inProgress) return;
    pollTimer.current = setTimeout(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [selection?.status, delivery, refresh]);

  async function validate() {
    if (!accessToken) return;
    setSubmitting(true);
    try {
      await publicApi.validateSelection(accessToken);
      await refresh();
    } catch (err) {
      if (handleClientApiError(err, token, router)) return;
      if (err instanceof ApiError && err.code === "empty_selection") {
        setFailure("Choisissez au moins une photo avant de valider.");
      } else {
        setFailure("La validation n'a pas abouti. Réessayez dans un instant.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function download() {
    if (!accessToken) return;
    setDownloading(true);
    try {
      const blob = await publicApi.downloadArchive(accessToken);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${collection?.title ?? "photos"}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (handleClientApiError(err, token, router)) return;
      setFailure("Le téléchargement n'a pas pu démarrer. Réessayez dans un instant.");
    } finally {
      setDownloading(false);
    }
  }

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Chargement de votre sélection…" />
      </div>
    );
  }

  if (sessionError || !session || !collection || !selection) {
    return (
      <div className="mx-auto max-w-lg px-4 py-24">
        <ErrorState message={sessionError ?? "Sélection indisponible."} />
      </div>
    );
  }

  const validated = selection.status === "validated";
  const ready = delivery?.ready === true;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
        {collection.studio_name}
      </p>
      <h1 className="mt-1 text-2xl font-semibold text-ink-900">
        {validated ? "Votre commande" : "Confirmer votre sélection"}
      </h1>

      {failure ? (
        <div className="mt-4">
          <Notice tone="danger" onDismiss={() => setFailure(null)}>
            {failure}
          </Notice>
        </div>
      ) : null}

      <Card className="mt-6">
        <p className="text-sm text-ink-600">Photos retenues</p>
        <p className="mt-1 text-4xl font-semibold text-ink-900">{selection.count}</p>
        {selection.items.some((item) => item.comment) ? (
          <div className="mt-4 border-t border-ink-100 pt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
              Vos commentaires
            </p>
            <ul className="mt-2 space-y-1 text-sm text-ink-700">
              {selection.items
                .filter((item) => item.comment)
                .map((item) => (
                  <li key={item.media_id}>
                    <span className="text-ink-500">Photo {item.media_id} —</span> {item.comment}
                  </li>
                ))}
            </ul>
          </div>
        ) : null}
      </Card>

      {!validated ? (
        <>
          <div className="mt-6">
            <Notice tone="warn">
              <p>
                <strong>Cette validation est définitive.</strong> Une fois confirmée, votre
                sélection ne pourra plus être modifiée et le studio préparera vos fichiers
                haute définition.
              </p>
            </Notice>
          </div>
          <div className="mt-6 flex items-center gap-3">
            <Button onClick={() => void validate()} loading={submitting} disabled={selection.count === 0}>
              Je confirme ma sélection
            </Button>
            <Link href={`/c/${token}`} className="text-sm text-ink-600 underline hover:no-underline">
              Revenir à mes photos
            </Link>
          </div>
        </>
      ) : (
        <div className="mt-6">
          {delivery?.status === "failed" ? (
            <Notice tone="danger">
              <p>
                La préparation de vos fichiers a rencontré un problème. Le studio en a été
                informé et revient vers vous.
              </p>
            </Notice>
          ) : ready ? (
            <Card>
              <p className="text-sm text-ink-600">
                {delivery?.item_count} photo{(delivery?.item_count ?? 0) > 1 ? "s" : ""} ·{" "}
                {formatSize(delivery?.byte_size ?? null)}
              </p>
              <p className="mt-1 text-lg font-semibold text-ink-900">Vos fichiers sont prêts.</p>
              <div className="mt-4">
                <Button onClick={() => void download()} loading={downloading}>
                  Télécharger mes photos
                </Button>
              </div>
            </Card>
          ) : (
            <Card>
              <Spinner label="Préparation de vos fichiers haute définition…" />
              <p className="mt-2 text-sm text-ink-600">
                Cette page se met à jour toute seule. Vous pouvez la laisser ouverte.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
