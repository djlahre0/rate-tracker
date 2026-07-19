"use client";

import type { ReactNode } from "react";

interface Props {
  id?: string;
  label?: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  children: ReactNode;
}

/** Native <select> styled to the desk: token colors, brass focus, custom chevron. */
export function Select({ id, label, value, onChange, disabled, children }: Props) {
  return (
    <label htmlFor={id} className="flex items-center gap-2">
      {label && <span className="eyebrow">{label}</span>}
      <span className="relative inline-flex">
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="appearance-none rounded-lg border border-line bg-surface py-2 pl-3 pr-8 text-sm text-ink transition-colors hover:border-line-strong focus:border-brass focus:outline-none disabled:opacity-50"
        >
          {children}
        </select>
        <svg
          aria-hidden
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M3 4.5L6 7.5L9 4.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </label>
  );
}
