"use client";

import { useEffect, useState } from "react";

import { relativeTime } from "@/lib/format";

interface Props {
  updatedAt: number | null;
  stale?: boolean;
}

/** The "alive" signal: a pulsing dot plus a freshness clock that ticks each second. */
export function LiveStatus({ updatedAt, stale = false }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const label = updatedAt ? `updated ${relativeTime(updatedAt, now)}` : "connecting…";
  const dot = stale ? "bg-muted" : "bg-gain";

  return (
    <span className="inline-flex items-center gap-2">
      <span className={`live-dot inline-block h-2 w-2 rounded-full ${dot}`} aria-hidden />
      <span className="font-mono text-xs tracking-wide text-muted">
        {stale ? "Reconnecting" : "Live"} · {label}
      </span>
    </span>
  );
}
