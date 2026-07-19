"use client";

import { useMemo, useState } from "react";

import { bpsDelta, ratePct, shortDate, shortRateType } from "@/lib/format";
import type { RateSummary } from "@/lib/types";
import { rateTypeLabel } from "@/lib/types";
import { DeltaChip } from "./DeltaChip";
import { Sparkline } from "./Sparkline";
import { StateWrapper } from "./StateWrapper";

type SortKey = "provider" | "rate_type" | "rate_value" | "change" | "effective_date";
type SortDir = "asc" | "desc";

interface Props {
  data: RateSummary[] | undefined;
  error: Error | undefined;
  isLoading: boolean;
  onRetry: () => void;
  type: string; // "" = all types
}

const COLUMNS: { key: SortKey | null; label: string; numeric?: boolean }[] = [
  { key: "provider", label: "Provider" },
  { key: "rate_type", label: "Type" },
  { key: "rate_value", label: "Rate", numeric: true },
  { key: "change", label: "30-day", numeric: true },
  { key: null, label: "Trend" },
  { key: "effective_date", label: "Updated", numeric: true },
];

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();
}

function compare(a: RateSummary, b: RateSummary, key: SortKey): number {
  switch (key) {
    case "rate_value":
      return parseFloat(a.rate_value) - parseFloat(b.rate_value);
    case "change":
      return parseFloat(a.change_30d ?? "0") - parseFloat(b.change_30d ?? "0");
    case "effective_date":
      return a.effective_date.localeCompare(b.effective_date);
    default:
      return String(a[key]).localeCompare(String(b[key]));
  }
}

export function RateBoard({ data, error, isLoading, onRetry, type }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("rate_value");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const rows = useMemo(() => {
    const filtered = (data ?? []).filter((r) => !type || r.rate_type === type);
    return filtered.sort((a, b) => {
      const c = compare(a, b, sortKey);
      return sortDir === "asc" ? c : -c;
    });
  }, [data, type, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      // Text columns read best ascending; figures default to highest-first.
      setSortDir(key === "provider" || key === "rate_type" ? "asc" : "desc");
    }
  }

  return (
    <StateWrapper
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      hasData={data !== undefined}
      skeleton={<BoardSkeleton />}
    >
      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <span aria-hidden className="block h-0.5 bg-brass-bright" />

        {/* Desktop / tablet: the board */}
        <div className="hidden overflow-x-auto sm:block">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line">
                {COLUMNS.map((col) => (
                  <th
                    key={col.label}
                    scope="col"
                    className={col.numeric ? "text-right" : "text-left"}
                    aria-sort={
                      col.key && sortKey === col.key
                        ? sortDir === "asc"
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                  >
                    {col.key ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(col.key as SortKey)}
                        className={`flex w-full items-center gap-1 px-4 py-3 eyebrow hover:text-ink ${
                          col.numeric ? "justify-end" : ""
                        }`}
                      >
                        {col.label}
                        <SortGlyph active={sortKey === col.key} dir={sortDir} />
                      </button>
                    ) : (
                      <span className="flex px-4 py-3 eyebrow">{col.label}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="px-4 py-12 text-center text-muted">
                    No rates to display yet.
                  </td>
                </tr>
              ) : (
                rows.map((row) => {
                  const { dir } = bpsDelta(row.change_30d);
                  return (
                    <tr
                      key={`${row.provider_slug}-${row.rate_type}`}
                      className="group border-b border-line last:border-0 transition-colors hover:bg-surface-2"
                    >
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-2.5">
                          <span
                            aria-hidden
                            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-line bg-surface-2 font-mono text-[0.6rem] font-medium text-ink-soft group-hover:border-brass/50 group-hover:text-brass"
                          >
                            {initials(row.provider)}
                          </span>
                          <span className="font-medium text-ink">{row.provider}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted">{rateTypeLabel(row.rate_type)}</td>
                      <td className="px-4 py-3 text-right font-mono text-[0.95rem] font-medium tabular-nums text-ink">
                        {ratePct(row.rate_value)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <DeltaChip change={row.change_30d} pct={row.change_30d_pct} />
                      </td>
                      <td className="px-4 py-3">
                        <span className="flex justify-start">
                          <Sparkline
                            data={row.spark}
                            dir={dir}
                            label={`${row.provider} ${shortRateType(row.rate_type)} 30-day trend`}
                          />
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-muted">
                        {shortDate(row.effective_date)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile: one card per series */}
        <ul className="divide-y divide-line sm:hidden">
          {rows.length === 0 ? (
            <li className="px-4 py-12 text-center text-muted">No rates to display yet.</li>
          ) : (
            rows.map((row) => {
              const { dir } = bpsDelta(row.change_30d);
              return (
                <li key={`${row.provider_slug}-${row.rate_type}`} className="px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">{row.provider}</p>
                      <p className="mt-0.5 text-sm text-muted">{rateTypeLabel(row.rate_type)}</p>
                    </div>
                    <p className="font-mono text-lg font-medium tabular-nums text-ink">
                      {ratePct(row.rate_value)}
                    </p>
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-3">
                    <DeltaChip change={row.change_30d} pct={row.change_30d_pct} />
                    <Sparkline data={row.spark} dir={dir} width={88} />
                    <span className="font-mono text-xs tabular-nums text-muted">
                      {shortDate(row.effective_date)}
                    </span>
                  </div>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </StateWrapper>
  );
}

function SortGlyph({ active, dir }: { active: boolean; dir: SortDir }) {
  return (
    <span aria-hidden className={active ? "text-brass" : "text-muted/50"}>
      {active ? (dir === "asc" ? "▲" : "▼") : "↕"}
    </span>
  );
}

function BoardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <span aria-hidden className="block h-0.5 bg-line" />
      <div className="p-4">
        <div className="mb-4 h-4 w-full animate-pulse rounded bg-surface-2" />
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="mb-3 h-6 w-full animate-pulse rounded bg-surface-2" />
        ))}
      </div>
    </div>
  );
}
