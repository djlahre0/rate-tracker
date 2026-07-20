import type { Paginated, Rate, RateSummary } from "./types";

// Client-side fetches run in the browser, so this has to be the host-reachable
// URL (localhost:8000), not the internal docker hostname. Use || rather than ??
// so an empty string (what an unset ${NEXT_PUBLIC_API_URL} bakes in at build time)
// falls back to the default instead of producing broken relative URLs. The
// trailing slash is stripped so we never emit "...//api/rates/...".
const BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function summaryUrl(type?: string): string {
  const suffix = type ? `?type=${encodeURIComponent(type)}` : "";
  return `${BASE}/api/rates/summary${suffix}`;
}

export function historyUrl(
  provider: string,
  type: string,
  from?: string,
  to?: string,
): string {
  // Daily granularity → one clean point per day for the 30-day line chart.
  const params = new URLSearchParams({ provider, type, granularity: "daily", limit: "366" });
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  return `${BASE}/api/rates/history?${params.toString()}`;
}

export type { Paginated, Rate, RateSummary };
