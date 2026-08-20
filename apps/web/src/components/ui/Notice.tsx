import clsx from "clsx";

export type NoticeTone = "ok" | "danger" | "warn" | "accent";

const TONE_CLASSES: Record<NoticeTone, string> = {
  ok: "border-ok-100 bg-ok-100/50 text-ok-600",
  danger: "border-danger-100 bg-danger-100/50 text-danger-600",
  warn: "border-warn-100 bg-warn-100/50 text-warn-600",
  accent: "border-accent-100 bg-accent-50 text-accent-700",
};

export function Notice({
  tone = "accent",
  children,
  onDismiss,
}: {
  tone?: NoticeTone;
  children: React.ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={clsx("flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm", TONE_CLASSES[tone])}
    >
      <div>{children}</div>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Fermer le message"
          className="shrink-0 text-current opacity-70 hover:opacity-100"
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}
