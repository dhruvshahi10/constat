"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  isTheme,
  themeFromParam,
  type Theme,
} from "@/lib/theme";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
};

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // storage may be unavailable inside a sandboxed iframe; the attribute
    // alone is enough for the page to render correctly
  }
}

function ThemeProviderInner({ children }: { children: React.ReactNode }) {
  const params = useSearchParams();
  const param = params.get("theme");
  const [theme, setThemeState] = React.useState<Theme>(() => {
    if (isTheme(param)) return param;
    if (typeof document !== "undefined") {
      const current = document.documentElement.getAttribute("data-theme");
      if (isTheme(current)) return current;
    }
    return DEFAULT_THEME;
  });

  // A ?theme= in the URL always wins, so the embedded host can force a theme.
  React.useEffect(() => {
    if (isTheme(param) && param !== theme) setThemeState(param);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [param]);

  React.useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // The Atlan handshake may hand us a theme after init.
  React.useEffect(() => {
    function onTheme(e: Event) {
      const next = (e as CustomEvent<string>).detail;
      if (isTheme(next)) setThemeState(next);
    }
    window.addEventListener("constat:theme", onTheme);
    return () => window.removeEventListener("constat:theme", onTheme);
  }, []);

  const value = React.useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme: (t) => setThemeState(themeFromParam(t)),
      toggleTheme: () => setThemeState((t) => (t === "constat" ? "native" : "constat")),
    }),
    [theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // useSearchParams needs a Suspense boundary during static rendering.
  return (
    <React.Suspense fallback={null}>
      <ThemeProviderInner>{children}</ThemeProviderInner>
    </React.Suspense>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}
