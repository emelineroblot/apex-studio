import { Fragment } from "react";
import { Modal } from "@/components/ui/Modal";

const SHORTCUTS: [string, string][] = [
  ["A", "Accepter l'engagement suggéré"],
  ["R", "Rejeter la lecture OCR"],
  ["1 – 9", "Rattacher à une autre suggestion listée"],
  ["← / →", "Naviguer entre les photos chargées"],
  ["Espace", "Marquer / démarquer pour un traitement en lot"],
  ["Entrée", "Appliquer les décisions en attente"],
  ["Retour arrière", "Annuler la décision de la photo affichée"],
  ["?", "Afficher/masquer cette aide"],
];

export function KeyboardHelpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title="Raccourcis clavier">
      <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-2 text-sm">
        {SHORTCUTS.map(([key, description]) => (
          <Fragment key={key}>
            <dt>
              <kbd className="rounded border border-ink-200 bg-ink-50 px-1.5 py-0.5 font-mono text-xs text-ink-700">
                {key}
              </kbd>
            </dt>
            <dd className="text-ink-600">{description}</dd>
          </Fragment>
        ))}
      </dl>
      <p className="mt-4 text-xs text-ink-500">
        Une action s&apos;applique aux photos marquées (Espace) si une sélection est en cours,
        sinon uniquement à la photo affichée. Le rattachement (1-9) reste toujours individuel :
        les suggestions diffèrent d&apos;une photo à l&apos;autre.
      </p>
    </Modal>
  );
}
