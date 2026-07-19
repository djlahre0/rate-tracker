"use client";

import { LiveStatus } from "./LiveStatus";
import { ThemeToggle } from "./ThemeToggle";

interface Props {
  updatedAt: number | null;
  stale?: boolean;
}

function BrandMark() {
  return (
    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-brass/50 bg-brass-soft">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M4 16l5-5 4 3 7-8"
          stroke="var(--color-brass-bright)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="20" cy="6" r="2" fill="var(--color-brass-bright)" />
      </svg>
    </span>
  );
}

export function TopBar({ updatedAt, stale }: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-paper/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <BrandMark />
          <div className="leading-tight">
            <p className="font-display text-base font-semibold tracking-tight text-ink">Rate Tracker</p>
            <p className="eyebrow mt-0.5">The rates desk</p>
          </div>
        </div>
        <div className="flex items-center gap-3 sm:gap-4">
          <span className="hidden sm:inline-flex">
            <LiveStatus updatedAt={updatedAt} stale={stale} />
          </span>
          <ThemeToggle />
        </div>
      </div>
      <div className="mx-auto max-w-6xl px-4 pb-2.5 sm:hidden">
        <LiveStatus updatedAt={updatedAt} stale={stale} />
      </div>
    </header>
  );
}
