export function ProgressBar({
  value,
  label,
}: {
  /** 0 à 1. */
  value: number;
  label: string;
}) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-ink-500">
        <span>{label}</span>
        <span>{percent} %</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-2 w-full overflow-hidden rounded-full bg-ink-100"
      >
        <div className="h-full rounded-full bg-accent-600 transition-all" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
