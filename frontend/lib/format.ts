// Formatting helpers for the rates desk. Numbers are the subject, so their
// presentation lives in one place: percentages to 2dp, movement in basis points
// (the unit a rates desk actually speaks), dates short, freshness relative.

export type Direction = "up" | "down" | "flat";

const MINUS = "−"; // real minus sign, aligns better than a hyphen

export function ratePct(value: string | number, dp = 2): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return Number.isFinite(n) ? `${n.toFixed(dp)}%` : "—";
}

/** A 30-day change (percentage points) expressed as basis points: 0.12 → "+12 bps". */
export function bpsDelta(changePp: string | number | null | undefined): {
  dir: Direction;
  bps: number | null;
  label: string;
} {
  if (changePp === null || changePp === undefined) {
    return { dir: "flat", bps: null, label: "—" };
  }
  const pp = typeof changePp === "string" ? parseFloat(changePp) : changePp;
  if (!Number.isFinite(pp)) return { dir: "flat", bps: null, label: "—" };
  const bps = Math.round(pp * 100);
  if (bps === 0) return { dir: "flat", bps: 0, label: "0 bps" };
  const dir: Direction = bps > 0 ? "up" : "down";
  const sign = bps > 0 ? "+" : MINUS;
  return { dir, bps, label: `${sign}${Math.abs(bps)} bps` };
}

/** Percentage change with an explicit sign: 2.46 → "+2.5%". */
export function pctDelta(pct: number | null | undefined, dp = 1): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return "";
  const sign = pct > 0 ? "+" : pct < 0 ? MINUS : "";
  return `${sign}${Math.abs(pct).toFixed(dp)}%`;
}

/** Tailwind classes for a movement direction (theme-aware semantic tokens). */
export function deltaClasses(dir: Direction): { text: string; chip: string } {
  if (dir === "up") return { text: "text-gain", chip: "bg-gain-soft text-gain" };
  if (dir === "down") return { text: "text-loss", chip: "bg-loss-soft text-loss" };
  return { text: "text-muted", chip: "bg-surface-2 text-muted" };
}

export function shortDate(iso: string): string {
  // date-only values parse as local midnight to avoid a UTC off-by-one.
  const d = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

const SHORT_RATE_TYPE: Record<string, string> = {
  "30yr_fixed_mortgage": "30y fixed",
  "15yr_fixed_mortgage": "15y fixed",
  "5yr_arm_mortgage": "5y ARM",
  "savings_1yr_fixed": "1y savings",
  "savings_easy_access": "Easy-access",
};

export function shortRateType(rateType: string): string {
  return SHORT_RATE_TYPE[rateType] ?? rateType;
}

/** Freshness for the live status: "8s ago", "3m ago". */
export function relativeTime(fromMs: number, nowMs: number): string {
  const s = Math.max(0, Math.round((nowMs - fromMs) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}
