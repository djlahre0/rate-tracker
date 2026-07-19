"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetcher, historyUrl } from "@/lib/api";
import { bpsDelta, ratePct, shortRateType } from "@/lib/format";
import type { Paginated, Rate } from "@/lib/types";
import useSWR from "swr";
import { DeltaChip } from "./DeltaChip";
import { StateWrapper } from "./StateWrapper";

interface Props {
  provider: string;
  type: string;
  providerName?: string;
}

const DIR_COLOR = {
  up: "var(--color-gain)",
  down: "var(--color-loss)",
  flat: "var(--color-brass-bright)",
} as const;

export function HistoryChart({ provider, type, providerName }: Props) {
  const key = provider && type ? historyUrl(provider, type) : null;
  const { data, error, isLoading, mutate } = useSWR<Paginated<Rate>, Error>(key, fetcher, {
    refreshInterval: 60_000,
    keepPreviousData: true, // update the line in place instead of flashing on filter change
  });

  const points = useMemo(() => {
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r) => ({ date: r.effective_date, value: parseFloat(r.rate_value) }));
  }, [data]);

  const current = points.length > 0 ? points[points.length - 1].value : null;
  const changePp =
    points.length >= 2 ? points[points.length - 1].value - points[0].value : null;
  const dir = bpsDelta(changePp).dir;
  const color = DIR_COLOR[dir];
  const gradientId = `spark-${dir}`;

  if (!provider || !type) {
    return (
      <div className="flex h-72 items-center justify-center rounded-xl border border-line bg-surface text-sm text-muted">
        Select a provider and rate type to chart its 30-day history.
      </div>
    );
  }

  return (
    <StateWrapper
      isLoading={isLoading}
      error={error}
      onRetry={() => mutate()}
      hasData={data !== undefined}
      skeleton={<div className="h-[340px] animate-pulse rounded-xl border border-line bg-surface-2" />}
    >
      <div className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <p className="eyebrow">Current · {shortRateType(type)}</p>
            <p className="mt-1.5 font-mono text-2xl font-medium tabular-nums text-ink">
              {current != null ? ratePct(current) : "—"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <DeltaChip change={changePp} size="md" />
            <span className="eyebrow">over 30 days</span>
          </div>
        </div>

        {points.length === 0 ? (
          <div className="flex h-64 items-center justify-center text-sm text-muted">
            No history in this window for {providerName ?? provider} · {shortRateType(type)}.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.22} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "var(--color-muted)", fontFamily: "var(--font-mono)" }}
                tickFormatter={(d: string) => d.slice(5)}
                minTickGap={28}
                stroke="var(--color-line)"
              />
              <YAxis
                tick={{ fontSize: 11, fill: "var(--color-muted)", fontFamily: "var(--font-mono)" }}
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => `${v.toFixed(1)}%`}
                width={52}
                stroke="var(--color-line)"
              />
              <Tooltip
                contentStyle={{
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-line)",
                  borderRadius: 10,
                  color: "var(--color-ink)",
                  fontSize: 12,
                  fontFamily: "var(--font-mono)",
                }}
                cursor={{ stroke: "var(--color-line-strong)", strokeWidth: 1 }}
                formatter={(value) => [`${Number(value ?? 0).toFixed(4)}%`, shortRateType(type)]}
                labelFormatter={(label) => `Effective ${label}`}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2}
                fill={`url(#${gradientId})`}
                dot={points.length < 2 ? { r: 3, fill: color } : false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </StateWrapper>
  );
}
