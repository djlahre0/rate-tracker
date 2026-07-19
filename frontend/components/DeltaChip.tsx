import { bpsDelta, deltaClasses, pctDelta } from "@/lib/format";

interface Props {
  /** 30-day change in percentage points (as the API returns it). */
  change: string | number | null;
  /** Optional percentage change, added to the hover title for context. */
  pct?: number | null;
  size?: "sm" | "md";
  className?: string;
}

const ARROW: Record<string, string> = { up: "▲", down: "▼", flat: "" };

/** Movement shown the way a rates desk says it: in basis points, with a direction. */
export function DeltaChip({ change, pct, size = "sm", className = "" }: Props) {
  const { dir, label } = bpsDelta(change);
  const { chip } = deltaClasses(dir);
  const pad = size === "md" ? "px-2 py-1 text-sm" : "px-1.5 py-0.5 text-xs";
  const title =
    dir === "flat"
      ? "No 30-day change"
      : `30-day change ${label}${pct != null ? ` (${pctDelta(pct)})` : ""}`;

  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-md font-mono tabular-nums ${pad} ${chip} ${className}`}
    >
      {dir !== "flat" && (
        <span aria-hidden className="text-[0.6em] leading-none">
          {ARROW[dir]}
        </span>
      )}
      {label}
    </span>
  );
}
