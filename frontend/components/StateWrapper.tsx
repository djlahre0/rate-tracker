"use client";

import type { ReactNode } from "react";

interface StateWrapperProps {
  isLoading: boolean;
  error: Error | undefined;
  onRetry: () => void;
  /** Skeleton shown while loading; pass a shape that matches the content. */
  skeleton: ReactNode;
  /**
   * True when content is already on screen (e.g. SWR still holds the last good
   * data). When set, a fetch error shows as a small banner above the children
   * instead of replacing them, so a failed 60s background refresh doesn't wipe
   * an already-populated board or chart.
   */
  hasData?: boolean;
  children: ReactNode;
}

/**
 * Renders the right state for a data fetch:
 *  - a content-shaped skeleton on the first load (no data yet),
 *  - a full error card with Retry when a fetch fails and there's nothing to show,
 *  - a small "couldn't refresh" banner above the still-visible content when a
 *    background refresh fails but we already have data (hasData),
 *  - otherwise the children.
 * Every fetch uses it, so nothing falls back to a bare spinner and a transient
 * refresh error never destroys data the user was already looking at.
 */
export function StateWrapper({
  isLoading,
  error,
  onRetry,
  skeleton,
  hasData = false,
  children,
}: StateWrapperProps) {
  if (error && !hasData) {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-xl border border-line bg-surface p-6"
      >
        <div>
          <p className="font-display text-base font-semibold text-loss">Couldn&apos;t load data</p>
          <p className="mt-1 text-sm text-muted">{error.message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-paper transition-opacity hover:opacity-90"
        >
          Try again
        </button>
      </div>
    );
  }

  if (isLoading && !hasData) {
    return <>{skeleton}</>;
  }

  return (
    <>
      {error && hasData ? (
        <div
          role="status"
          className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm"
        >
          <span className="text-muted">Couldn&apos;t refresh — showing the last loaded rates.</span>
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:text-ink"
          >
            Retry
          </button>
        </div>
      ) : null}
      {children}
    </>
  );
}
