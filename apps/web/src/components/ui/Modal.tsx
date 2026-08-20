"use client";

import { useEffect, useRef } from "react";

/**
 * `<dialog>` natif : focus trap et fermeture `Échap` gérés par le navigateur, base
 * d'accessibilité solide sans dépendance. `onClose` est appelé aussi bien par le bouton
 * de fermeture que par `Échap`/clic sur le fond (événement natif `close`).
 */
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const handleClose = () => onClose();
    node.addEventListener("close", handleClose);
    return () => node.removeEventListener("close", handleClose);
  }, [onClose]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="modal-title"
      className="w-full max-w-lg rounded-xl border border-ink-100 bg-white p-0 shadow-xl backdrop:bg-ink-950/50"
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="flex items-center justify-between border-b border-ink-100 px-5 py-4">
        <h2 id="modal-title" className="text-base font-semibold text-ink-900">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fermer"
          className="rounded-full p-1.5 text-ink-500 hover:bg-ink-100 hover:text-ink-800"
        >
          ✕
        </button>
      </div>
      <div className="max-h-[75vh] overflow-y-auto px-5 py-4">{children}</div>
    </dialog>
  );
}
