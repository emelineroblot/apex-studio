"use client";

import { useCallback, useEffect, useState } from "react";
import * as reviewApi from "@/lib/api/resources/review";
import * as settingsApi from "@/lib/api/resources/settings";
import * as shootingsApi from "@/lib/api/resources/shootings";
import type { ReviewItem, ShootingSummary } from "@/lib/api/types";
import {
  clampIndex,
  nextUndecidedIndex,
  resolveBatchTargets,
  stageDecisions,
  toReviewDecisionsPayload,
  toggleSelection,
  unstageDecision,
  type DecisionMap,
} from "@/lib/review/batch";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { ReviewCard } from "@/components/review/ReviewCard";
import { ReviewFilmstrip } from "@/components/review/ReviewFilmstrip";
import { KeyboardHelpModal } from "@/components/review/KeyboardHelpModal";

const PAGE_LIMIT = 30;

export default function ReviewPage() {
  const [shootingId, setShootingId] = useState<number | null>(null);
  const [shootings, setShootings] = useState<ShootingSummary[]>([]);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [remainingTotal, setRemainingTotal] = useState(0);
  /** Capturé au premier chargement de chaque filtre — dénominateur stable de la barre de
   * progression (`remainingTotal` seul redescend au fil des envois, sans repère de départ). */
  const [initialRemaining, setInitialRemaining] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [thresholds, setThresholds] = useState({ high: 0.8, low: 0.45 });

  const [decisions, setDecisions] = useState<DecisionMap>(new Map());
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [focusIndex, setFocusIndex] = useState(0);
  const [showHelp, setShowHelp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);

  useEffect(() => {
    shootingsApi.list({ limit: 100 }).then((page) => setShootings(page.items));
    settingsApi.getOcr().then((s) => setThresholds({ high: s.high, low: s.low }));
  }, []);

  const loadFirstPage = useCallback(() => {
    setLoading(true);
    setError(null);
    setDecisions(new Map());
    setSelectedIds(new Set());
    setFocusIndex(0);
    reviewApi
      .queue({ shooting_id: shootingId, limit: PAGE_LIMIT })
      .then((res) => {
        setItems(res.items);
        setRemainingTotal(res.remaining);
        setInitialRemaining(res.remaining);
        setNextCursor(res.next_cursor);
        setLoading(false);
      })
      .catch((err) => {
        setError(err);
        setLoading(false);
      });
  }, [shootingId]);

  useEffect(() => {
    loadFirstPage();
  }, [loadFirstPage]);

  const loadMore = useCallback(() => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    reviewApi
      .queue({ shooting_id: shootingId, cursor: nextCursor, limit: PAGE_LIMIT })
      .then((res) => {
        setItems((prev) => [...prev, ...res.items]);
        setRemainingTotal(res.remaining);
        setNextCursor(res.next_cursor);
        setLoadingMore(false);
      })
      .catch((err) => {
        setError(err);
        setLoadingMore(false);
      });
  }, [shootingId, nextCursor, loadingMore]);

  const focused = items[focusIndex] as ReviewItem | undefined;

  const applyToTargets = useCallback(
    (action: "accept" | "reject" | "reassign", engagementId: number | null = null) => {
      if (!focused) return;
      const targets = resolveBatchTargets(selectedIds, focused.candidate_id);
      if (targets.length === 0) return;
      const nextDecisions = stageDecisions(decisions, targets, action, engagementId);
      const ids = items.map((i) => i.candidate_id);
      setDecisions(nextDecisions);
      setSelectedIds(new Set());
      setFocusIndex((current) => nextUndecidedIndex(ids, nextDecisions, current, 1));
    },
    [focused, selectedIds, items, decisions],
  );

  const submitDecisions = useCallback(() => {
    if (decisions.size === 0) return;
    setSubmitting(true);
    setSubmitNotice(null);
    const payload = toReviewDecisionsPayload(decisions);
    reviewApi
      .decide(payload)
      .then((res) => {
        const appliedIds = new Set(payload.map((d) => d.candidate_id));
        setItems((prev) => prev.filter((i) => !appliedIds.has(i.candidate_id)));
        setDecisions(new Map());
        setSelectedIds(new Set());
        setFocusIndex(0);
        setRemainingTotal(res.remaining);
        setSubmitting(false);
        const parts = [`${res.applied} décision${res.applied > 1 ? "s" : ""} appliquée${res.applied > 1 ? "s" : ""}`];
        if (res.skipped > 0) parts.push(`${res.skipped} ignorée${res.skipped > 1 ? "s" : ""}`);
        setSubmitNotice(parts.join(", ") + ".");
      })
      .catch((err) => {
        setError(err);
        setSubmitting(false);
      });
  }, [decisions]);

  // Recharge une nouvelle page quand la file locale se vide mais qu'il en reste côté serveur —
  // garde le flux clavier continu sans action de l'utilisateur.
  useEffect(() => {
    if (!loading && items.length < 5 && nextCursor && !loadingMore) loadMore();
  }, [items.length, nextCursor, loading, loadingMore, loadMore]);

  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const isTyping = target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
      if (isTyping) return;

      if (e.key === "?") {
        e.preventDefault();
        setShowHelp((v) => !v);
        return;
      }
      if (!focused) return;

      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        if (focused.suggested_engagement != null || selectedIds.size > 0) applyToTargets("accept");
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        applyToTargets("reject");
      } else if (/^[1-9]$/.test(e.key)) {
        e.preventDefault();
        const alt = focused.other_engagements[Number(e.key) - 1];
        if (alt) applyToTargets("reassign", alt.id);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setFocusIndex((i) => clampIndex(i + 1, items.length));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setFocusIndex((i) => clampIndex(i - 1, items.length));
      } else if (e.key === " ") {
        e.preventDefault();
        setSelectedIds((prev) => toggleSelection(prev, focused.candidate_id));
      } else if (e.key === "Backspace") {
        e.preventDefault();
        setDecisions((prev) => unstageDecision(prev, focused.candidate_id));
      } else if (e.key === "Enter") {
        e.preventDefault();
        submitDecisions();
      }
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [focused, selectedIds, items, applyToTargets, submitDecisions]);

  return (
    <div>
      <PageHeader
        title="File de validation OCR"
        description="Photos dont le numéro lu est incertain, ou incohérent avec les engagements du shooting."
        actions={
          <>
            <label className="flex items-center gap-2 text-sm text-ink-600">
              Shooting
              <select
                value={shootingId ?? ""}
                onChange={(e) => setShootingId(e.target.value ? Number(e.target.value) : null)}
                className="rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm"
              >
                <option value="">Tous</option>
                {shootings.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </select>
            </label>
            <Button variant="secondary" size="sm" onClick={() => setShowHelp(true)}>
              Aide clavier (?)
            </Button>
          </>
        }
      />

      {submitNotice ? (
        <Notice tone="ok" onDismiss={() => setSubmitNotice(null)}>
          {submitNotice}
        </Notice>
      ) : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={loadFirstPage} /> : null}

      {loading ? (
        <Spinner label="Chargement de la file de validation…" />
      ) : items.length === 0 && decisions.size === 0 ? (
        <EmptyState
          title="File de validation vide"
          description="Aucun candidat OCR n'attend d'arbitrage pour ce filtre — tout est déjà rattaché automatiquement ou déjà tranché."
        />
      ) : (
        <div className="flex flex-col gap-4">
          <ProgressBar
            value={initialRemaining > 0 ? 1 - remainingTotal / initialRemaining : 1}
            label={`${remainingTotal} restant${remainingTotal > 1 ? "s" : ""} · ${decisions.size} en attente d'envoi`}
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={submitDecisions} disabled={decisions.size === 0} loading={submitting}>
              Appliquer le lot ({decisions.size}) — Entrée
            </Button>
            {selectedIds.size > 0 ? (
              <span className="text-sm text-ink-600">
                {selectedIds.size} marquée{selectedIds.size > 1 ? "s" : ""} pour un traitement en lot (Espace)
              </span>
            ) : null}
          </div>

          {focused ? (
            <ReviewCard
              item={focused}
              thresholds={thresholds}
              decision={decisions.get(focused.candidate_id)}
              selected={selectedIds.has(focused.candidate_id)}
              onNumberShortcut={(engagementId) => applyToTargets("reassign", engagementId)}
            />
          ) : (
            <EmptyState title="Tout est décidé" description="Appliquez le lot pour envoyer les décisions en attente." />
          )}

          <ReviewFilmstrip
            items={items}
            focusIndex={focusIndex}
            decisions={decisions}
            selectedIds={selectedIds}
            onFocus={setFocusIndex}
            onToggleSelect={(id) => setSelectedIds((prev) => toggleSelection(prev, id))}
          />

          {nextCursor ? (
            <div className="flex justify-center">
              <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
                Charger plus
              </Button>
            </div>
          ) : null}
        </div>
      )}

      <KeyboardHelpModal open={showHelp} onClose={() => setShowHelp(false)} />
    </div>
  );
}
