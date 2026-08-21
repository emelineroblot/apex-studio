"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Commentaire libre attaché à une photo sélectionnée.
 *
 * **Sauvegarde optimiste, différée.** Le champ ne déclenche pas un appel par frappe : il
 * attend une pause de saisie. Un client qui écrit « la 3 est floue, préférer celle-ci »
 * produirait sinon une trentaine de requêtes pour un seul commentaire. La valeur affichée
 * est toujours celle qu'il vient de taper — jamais celle du serveur qui reviendrait
 * écraser sa frappe en cours.
 *
 * En cas d'échec, on le dit et on garde le texte : perdre le commentaire d'un client
 * parce que le réseau a hoqueté serait pire que l'afficher comme non enregistré.
 */
const DEBOUNCE_MS = 700;

export function PhotoComment({
  value,
  onSave,
  disabled,
}: {
  value: string | null;
  onSave: (comment: string | null) => Promise<void>;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState(value ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef(value ?? "");

  // Une valeur venue du serveur ne doit remplacer le brouillon que si l'utilisateur n'a
  // rien tapé entre-temps : sinon un rechargement de liste effacerait sa phrase en cours.
  useEffect(() => {
    if (draft === lastSaved.current) {
      setDraft(value ?? "");
      lastSaved.current = value ?? "";
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function schedule(next: string) {
    setDraft(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const cleaned = next.trim();
      if (cleaned === lastSaved.current.trim()) {
        setState("idle");
        return;
      }
      setState("saving");
      onSave(cleaned || null)
        .then(() => {
          lastSaved.current = cleaned;
          setState("saved");
        })
        .catch(() => setState("failed"));
    }, DEBOUNCE_MS);
  }

  return (
    <div className="mt-2">
      <label className="sr-only" htmlFor={`comment-${value ?? "new"}`}>
        Commentaire sur cette photo
      </label>
      <textarea
        id={`comment-${value ?? "new"}`}
        value={draft}
        disabled={disabled}
        onChange={(event) => schedule(event.target.value)}
        rows={2}
        placeholder="Une précision pour le studio ?"
        className="w-full rounded-md border border-ink-200 px-2 py-1.5 text-xs text-ink-800 placeholder:text-ink-400 focus-visible:outline-2 focus-visible:outline-accent-600 disabled:bg-ink-50 disabled:text-ink-400"
      />
      <p
        className="mt-1 h-4 text-[11px]"
        role="status"
        aria-live="polite"
      >
        {state === "saving" ? <span className="text-ink-500">Enregistrement…</span> : null}
        {state === "saved" ? <span className="text-ok-600">Enregistré</span> : null}
        {state === "failed" ? (
          <span className="text-danger-600">Non enregistré — votre texte est conservé.</span>
        ) : null}
      </p>
    </div>
  );
}
