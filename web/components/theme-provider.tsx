"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
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

function themeFromUrl(): Theme | null {
  try {
    const t = new URLSearchParams(window.location.search).get("theme");
    return isTheme(t) ? t : null;
  } catch {
    return null;
  }
}

/**
 * Theme state. The boot script in the root layout has already set
 * data-theme before first paint (from ?theme=, then storage, then the
 * default). This provider adopts that value on mount and owns it after.
 *
 * It reads ?theme= from window.location rather than useSearchParams on
 * purpose: useSearchParams would force a Suspense boundary around the whole
 * app, which turns every page into client-only rendering and makes
 * notFound() answer 200 instead of 404.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setThemeState] = React.useState<Theme>(DEFAULT_THEME);
  const adopted = React.useRef(false);

  // Adopt what the boot script chose; re-check ?theme= on client navigation
  // so a link carrying ?theme= still switches the theme.
  React.useEffect(() => {
    const fromUrl = themeFromUrl();
    if (!adopted.current) {
      adopted.current = true;
      const current = document.documentElement.getAttribute("data-theme");
      setThemeState(fromUrl ?? (isTheme(current) ? current : DEFAULT_THEME));
      return;
    }
    if (fromUrl) setThemeState(fromUrl);
  }, [pathname]);

  React.useEffect(() => {
    if (adopted.current) applyTheme(theme);
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

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}
