import clsx from "clsx";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-ink-100 bg-white p-5 shadow-[0_1px_2px_rgba(11,15,23,0.04)]",
        className,
      )}
    >
      {children}
    </div>
  );
}
