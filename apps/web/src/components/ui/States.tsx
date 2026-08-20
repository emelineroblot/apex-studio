import { Button } from "@/components/ui/Button";

export function Spinner({ label = "Chargement…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-10 text-sm text-ink-500">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-ink-300 border-t-accent-600"
        aria-hidden="true"
      />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-ink-200 bg-white/60 px-6 py-14 text-center">
      {icon}
      <p className="text-sm font-medium text-ink-800">{title}</p>
      {description ? <p className="max-w-md text-sm text-ink-500">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-xl border border-danger-100 bg-danger-100/40 px-5 py-5 text-sm text-danger-600"
    >
      <p className="font-medium">{message}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Réessayer
        </Button>
      ) : null}
    </div>
  );
}
