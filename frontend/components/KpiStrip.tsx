import { bpsDelta, deltaClasses, ratePct, shortRateType } from "@/lib/format";
import type { RateSummary } from "@/lib/types";
import { DeltaChip } from "./DeltaChip";
import { StatTile } from "./StatTile";

interface Props {
  data: RateSummary[] | undefined;
}

function extreme(
  rows: RateSummary[],
  rateType: string,
  pick: "min" | "max",
): RateSummary | null {
  const candidates = rows.filter((r) => r.rate_type === rateType);
  if (candidates.length === 0) return null;
  return candidates.reduce((best, r) => {
    const a = parseFloat(r.rate_value);
    const b = parseFloat(best.rate_value);
    return (pick === "min" ? a < b : a > b) ? r : best;
  });
}

/**
 * Market highlights across every series. "Best" is framed per product family —
 * a borrower wants the lowest mortgage, a saver the highest savings rate — so the
 * headline numbers are unambiguous rather than a bare min/max.
 */
export function KpiStrip({ data }: Props) {
  if (!data) return <KpiSkeleton />;

  const lowestMortgage = extreme(data, "30yr_fixed_mortgage", "min");
  const highestSavings = extreme(data, "savings_1yr_fixed", "max");

  const moved = data.filter((r) => r.change_30d != null);
  const biggestMove =
    moved.length > 0
      ? moved.reduce((best, r) =>
          Math.abs(parseFloat(r.change_30d as string)) >
          Math.abs(parseFloat(best.change_30d as string))
            ? r
            : best,
        )
      : null;

  const providerCount = new Set(data.map((r) => r.provider_slug)).size;
  const moveDir = biggestMove ? bpsDelta(biggestMove.change_30d).dir : "flat";

  return (
    <section aria-label="Market highlights" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatTile
        accent
        label="Lowest 30-yr fixed"
        value={lowestMortgage ? ratePct(lowestMortgage.rate_value) : "—"}
        sub={
          lowestMortgage ? (
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="text-ink-soft">{lowestMortgage.provider}</span>
              <DeltaChip change={lowestMortgage.change_30d} pct={lowestMortgage.change_30d_pct} />
            </span>
          ) : (
            "No data"
          )
        }
      />
      <StatTile
        label="Highest 1-yr savings"
        value={highestSavings ? ratePct(highestSavings.rate_value) : "—"}
        sub={
          highestSavings ? (
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="text-ink-soft">{highestSavings.provider}</span>
              <DeltaChip change={highestSavings.change_30d} pct={highestSavings.change_30d_pct} />
            </span>
          ) : (
            "No data"
          )
        }
      />
      <StatTile
        label="Biggest 30-day move"
        value={
          biggestMove ? (
            <span className={deltaClasses(moveDir).text}>{bpsDelta(biggestMove.change_30d).label}</span>
          ) : (
            "—"
          )
        }
        sub={
          biggestMove ? (
            <span className="text-ink-soft">
              {biggestMove.provider} · {shortRateType(biggestMove.rate_type)}
            </span>
          ) : (
            "Quiet market"
          )
        }
      />
      <StatTile
        label="Providers tracked"
        value={providerCount || "—"}
        sub={<span className="text-ink-soft">{data.length} rate series</span>}
      />
    </section>
  );
}

function KpiSkeleton() {
  return (
    <section aria-hidden className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-[104px] animate-pulse rounded-xl border border-line bg-surface-2" />
      ))}
    </section>
  );
}
