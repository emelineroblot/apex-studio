import { useId } from "react";
import clsx from "clsx";

type FieldProps = {
  label: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  children: (inputProps: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => React.ReactNode;
};

/** Enveloppe label + champ + aide + erreur, id relié pour l'accessibilité (WCAG). */
export function Field({ label, hint, error, required, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink-800">
        {label}
        {required ? <span className="text-danger-600" aria-hidden="true"> *</span> : null}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": Boolean(error) })}
      {hint && !error ? (
        <p id={hintId} className="text-xs text-ink-500">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-xs font-medium text-danger-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const inputBase =
  "w-full rounded-lg border px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-1";

/**
 * Les couleurs vivent dans une variante, **jamais dans une classe ajoutée par-dessus**.
 *
 * Empiler `bg-ink-800` sur une base qui porte déjà `bg-white` ne produit pas la couleur
 * qu'on croit : entre deux utilitaires Tailwind de même propriété, ce n'est pas l'ordre
 * dans l'attribut `class` qui tranche, mais celui du CSS généré. Sur l'écran de connexion,
 * `bg-white` et `text-white` gagnaient tous les deux — champs blancs, texte blanc, saisie
 * invisible. Le formulaire fonctionnait parfaitement, on ne voyait simplement rien.
 */
const TONE_CLASSES = {
  light:
    "border-ink-200 bg-white text-ink-900 placeholder:text-ink-400 focus-visible:outline-accent-600 disabled:bg-ink-50 disabled:text-ink-400",
  dark: "border-ink-700 bg-ink-800 text-white placeholder:text-ink-500 focus-visible:outline-accent-500 disabled:bg-ink-900 disabled:text-ink-500",
} as const;

export type InputTone = keyof typeof TONE_CLASSES;

export function inputClassName(className?: string, tone: InputTone = "light"): string {
  return clsx(inputBase, TONE_CLASSES[tone], className);
}
