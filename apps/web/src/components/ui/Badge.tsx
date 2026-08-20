import clsx from "clsx";

export type BadgeTone = "neutral" | "ok" | "warn" | "danger" | "accent";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-ink-100 text-ink-700",
  ok: "bg-ok-100 text-ok-600",
  warn: "bg-warn-100 text-warn-600",
  danger: "bg-danger-100 text-danger-600",
  accent: "bg-accent-100 text-accent-700",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
