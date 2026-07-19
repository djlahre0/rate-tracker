import type { ReactNode } from "react";

interface Props {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  /** The one signature tile gets the brass treatment; the rest stay quiet. */
  accent?: boolean;
  className?: string;
}

export function StatTile({ label, value, sub, accent = false, className = "" }: Props) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border bg-surface p-4 sm:p-5 ${
        accent ? "border-brass/40" : "border-line"
      } ${className}`}
    >
      {/* A brass top-rule marks the signature tile; others get a hairline. */}
      <span
        aria-hidden
        className={`absolute inset-x-0 top-0 h-0.5 ${accent ? "bg-brass-bright" : "bg-line"}`}
      />
      <p className="eyebrow">{label}</p>
      <p className="mt-2.5 font-display text-2xl font-semibold leading-none tracking-tight text-ink tabular-nums sm:text-[1.75rem]">
        {value}
      </p>
      {sub ? <div className="mt-2 text-sm text-muted">{sub}</div> : null}
    </div>
  );
}
