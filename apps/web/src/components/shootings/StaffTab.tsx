"use client";

import { useState } from "react";
import type { ShootingOut } from "@/lib/api/types";
import * as shootingsApi from "@/lib/api/resources/shootings";
import * as usersApi from "@/lib/api/resources/users";
import { useAsync } from "@/hooks/useAsync";
import { ROLE_LABELS } from "@/lib/labels";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";

export function StaffTab({
  shooting,
  canWrite,
  onUpdated,
}: {
  shooting: ShootingOut;
  canWrite: boolean;
  onUpdated: () => void;
}) {
  const { data: users, loading, error, reload } = useAsync(() => usersApi.listStaff(), []);
  const [selected, setSelected] = useState<Set<number> | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const current = selected ?? new Set(shooting.staff.map((s) => s.user_id));

  function toggle(userId: number) {
    const next = new Set(current);
    if (next.has(userId)) next.delete(userId);
    else next.add(userId);
    setSelected(next);
    setSaved(false);
  }

  async function handleSave() {
    setSubmitting(true);
    setSaveError(null);
    try {
      await shootingsApi.setStaff(shooting.id, Array.from(current));
      setSaved(true);
      setSelected(null);
      onUpdated();
    } catch (err) {
      setSaveError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <Spinner label="Chargement de l'équipe…" />;
  if (error) {
    return <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} />;
  }
  if (!users || users.length === 0) {
    return <EmptyState title="Aucun employé disponible" />;
  }

  return (
    <Card>
      {!canWrite ? (
        <p className="mb-3 text-xs text-ink-500">Lecture seule — seul le dirigeant modifie l&apos;affectation.</p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {users.map((u) => (
          <li key={u.id} className="flex items-center gap-3 rounded-lg border border-ink-100 px-3 py-2.5">
            <input
              type="checkbox"
              id={`staff-${u.id}`}
              checked={current.has(u.id)}
              disabled={!canWrite}
              onChange={() => toggle(u.id)}
              className="h-4 w-4 accent-accent-600"
            />
            <label htmlFor={`staff-${u.id}`} className="flex-1 text-sm text-ink-800">
              {u.full_name}
              <span className="ml-2 text-xs text-ink-400">{ROLE_LABELS[u.role]}</span>
            </label>
          </li>
        ))}
      </ul>

      {canWrite ? (
        <div className="mt-4 flex items-center gap-3">
          <Button size="sm" loading={submitting} disabled={selected === null} onClick={handleSave}>
            Enregistrer l&apos;affectation
          </Button>
          {saved ? <Notice tone="ok">Équipe mise à jour.</Notice> : null}
        </div>
      ) : null}
      {saveError ? (
        <div className="mt-3">
          <Notice tone="danger">{saveError}</Notice>
        </div>
      ) : null}
    </Card>
  );
}
