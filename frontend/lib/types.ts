export interface Rate {
  provider: string;
  provider_slug: string;
  rate_type: string;
  rate_value: string; // DRF DecimalField serializes as a string
  currency: string;
  effective_date: string;
  observed_at: string;
  ingested_at: string;
}

// GET /api/rates/summary — latest rate plus its ~30-day movement.
export interface RateSummary {
  provider: string;
  provider_slug: string;
  rate_type: string;
  currency: string;
  rate_value: string; // string decimal, like Rate
  effective_date: string;
  ingested_at: string;
  change_30d: string | null; // percentage points; null when the window is too short
  change_30d_pct: number | null;
  spark: number[]; // oldest → newest, ≤ 30 points
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const RATE_TYPES = [
  "30yr_fixed_mortgage",
  "15yr_fixed_mortgage",
  "5yr_arm_mortgage",
  "savings_1yr_fixed",
  "savings_easy_access",
] as const;

export type RateType = (typeof RATE_TYPES)[number];

// Product families — savings rates you want high, mortgage rates you want low.
// Used to frame the KPI highlights ("best" means opposite things per family).
export const MORTGAGE_TYPES: ReadonlySet<string> = new Set([
  "30yr_fixed_mortgage",
  "15yr_fixed_mortgage",
  "5yr_arm_mortgage",
]);

export function isSavings(rateType: string): boolean {
  return rateType.startsWith("savings");
}

export function rateTypeLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bArm\b/g, "ARM"); // keep the mortgage acronym uppercased
}
