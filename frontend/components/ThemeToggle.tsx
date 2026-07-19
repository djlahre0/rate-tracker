"use client";

import { useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";
const ORDER: Theme[] = ["system", "light", "dark"];

function apply(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
    localStorage.removeItem("rt-theme");
  } else {
    root.setAttribute("data-theme", theme);
    localStorage.setItem("rt-theme", theme);
  }
}

const ICON: Record<Theme, React.ReactNode> = {
  system: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="4" width="18" height="12" rx="1.5" />
      <path d="M8 20h8M12 16v4" strokeLinecap="round" />
    </svg>
  ),
  light: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" strokeLinecap="round" />
    </svg>
  ),
  dark: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" strokeLinejoin="round" />
    </svg>
  ),
};

const NEXT_LABEL: Record<Theme, string> = {
  system: "Match system",
  light: "Light",
  dark: "Dark",
};

/** Cycles system → light → dark. "system" leaves data-theme unset so the OS decides. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem("rt-theme");
    setTheme(saved === "light" || saved === "dark" ? saved : "system");
  }, []);

  function cycle() {
    const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setTheme(next);
    apply(next);
  }

  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={`Theme: ${NEXT_LABEL[theme]}. Activate to change.`}
      title={`Theme: ${NEXT_LABEL[theme]}`}
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
    >
      {mounted ? ICON[theme] : <span className="h-4 w-4" aria-hidden />}
    </button>
  );
}
