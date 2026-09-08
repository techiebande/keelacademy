"use client";

/* eslint-disable react-hooks/set-state-in-effect -- hydrating from localStorage after mount is intentional, and placeholder swap avoids hydration mismatch */
import { useEffect, useState } from "react";
import { useServerInsertedHTML } from "next/navigation";

type Theme = "dark" | "light";

function getStoredTheme(): Theme | null {
  try {
    const raw = localStorage.getItem("keel-theme");
    if (raw === "light" || raw === "dark") return raw;
  } catch {
    // ignore
  }
  return null;
}

function getPreferredTheme(): Theme {
  const stored = getStoredTheme();
  if (stored) return stored;
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
}

function applyTheme(theme: Theme) {
  const html = document.documentElement;
  if (theme === "light") html.setAttribute("data-theme", "light");
  else html.removeAttribute("data-theme");
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const initial = getPreferredTheme();
    setTheme(initial);
    applyTheme(initial);
    setMounted(true);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    try {
      localStorage.setItem("keel-theme", next);
    } catch {
      // ignore
    }
  };

  // Prevent hydration mismatch: render placeholder until mounted, then real button.
  if (!mounted) {
    return (
      <button type="button" className="theme-toggle" aria-label="Toggle reading theme" disabled>
        <span aria-hidden>◐</span> Reading mode
      </button>
    );
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} reading mode`}
      aria-pressed={theme === "light"}
      onClick={toggle}
    >
      <span aria-hidden>{theme === "dark" ? "☾" : "☀"}</span>
      {theme === "dark" ? "Light mode" : "Dark mode"}
    </button>
  );
}

// Inline script to set theme before React hydrates, avoiding flash.
export const themeInitScript = `(function(){try{var s=localStorage.getItem('keel-theme');var t=s||(window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');if(t==='light')document.documentElement.setAttribute('data-theme','light');}catch(e){}})();`;

export function ThemeScript() {
  useServerInsertedHTML(() => (
    <script
      dangerouslySetInnerHTML={{
        __html: themeInitScript,
      }}
    />
  ));
  return null;
}
