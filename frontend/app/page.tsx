"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { HistoryChart } from "@/components/HistoryChart";
import { KpiStrip } from "@/components/KpiStrip";
import type { ProviderOption } from "@/components/ProviderTypePicker";
import { ProviderTypePicker } from "@/components/ProviderTypePicker";
import { RateBoard } from "@/components/RateBoard";
import { TopBar } from "@/components/TopBar";
import { TypeFilter } from "@/components/TypeFilter";
import { fetcher, summaryUrl } from "@/lib/api";
import type { RateSummary } from "@/lib/types";
import { RATE_TYPES } from "@/lib/types";

export default function DashboardPage() {
  const [tableType, setTableType] = useState("");
  const [chartProvider, setChartProvider] = useState("");
  const [chartType, setChartType] = useState<string>(RATE_TYPES[0]);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  // One /summary fetch drives the KPI strip, the comparison board and the chart's
  // provider list. Type filtering happens client-side, so it's instant.
  const { data, error, isLoading, mutate } = useSWR<RateSummary[], Error>(summaryUrl(), fetcher, {
    refreshInterval: 60_000,
    onSuccess: () => setUpdatedAt(Date.now()),
  });

  const providers: ProviderOption[] = useMemo(() => {
    if (!data) return [];
    const byslug = new Map<string, string>();
    for (const r of data) byslug.set(r.provider_slug, r.provider);
    return [...byslug.entries()]
      .map(([slug, name]) => ({ slug, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [data]);

  useEffect(() => {
    if (!chartProvider && providers.length > 0) setChartProvider(providers[0].slug);
  }, [providers, chartProvider]);

  const chartProviderName = providers.find((p) => p.slug === chartProvider)?.name;

  return (
    <div className="min-h-dvh">
      <TopBar updatedAt={updatedAt} stale={!!error && data !== undefined} />

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <h1 className="sr-only">Rate Tracker — mortgage and savings rates dashboard</h1>

        <section className="mb-9 animate-rise">
          <KpiStrip data={data} />
        </section>

        <section className="mb-11">
          <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
              Rate comparison
            </h2>
            <TypeFilter id="table-type" value={tableType} onChange={setTableType} label="Filter" />
          </div>
          <RateBoard
            data={data}
            error={error}
            isLoading={isLoading}
            onRetry={() => mutate()}
            type={tableType}
          />
        </section>

        <section>
          <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
              30-day history
            </h2>
            {providers.length > 0 && (
              <ProviderTypePicker
                providers={providers}
                provider={chartProvider}
                type={chartType}
                onProviderChange={setChartProvider}
                onTypeChange={setChartType}
              />
            )}
          </div>
          <HistoryChart provider={chartProvider} type={chartType} providerName={chartProviderName} />
        </section>

        <footer className="mt-14 border-t border-line pt-5 text-xs text-muted">
          <p>
            Rate Tracker · rates cleaned, validated and served from a typed API. Movement shown in
            basis points (1&nbsp;bp&nbsp;=&nbsp;0.01%).
          </p>
        </footer>
      </main>
    </div>
  );
}
