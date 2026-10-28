export type Theme = "constat" | "native";

export const THEMES: readonly Theme[] = ["constat", "native"] as const;
export const DEFAULT_THEME: Theme = "constat";
export const THEME_STORAGE_KEY = "constat.theme";

export function isTheme(value: unknown): value is Theme {
  return value === "constat" || value === "native";
}

/** Resolves the theme from a ?theme= value, falling back to the default. */
export function themeFromParam(value: string | null | undefined): Theme {
  return isTheme(value) ? value : DEFAULT_THEME;
}

/**
 * Inline script run before hydration so the first paint already carries the
 * right data-theme. Order: ?theme= in the URL, then the stored choice, then
 * the default. Kept dependency-free and tiny on purpose.
 */
export const THEME_BOOT_SCRIPT = `(function(){var d=document.documentElement;var t=null;try{t=new URLSearchParams(location.search).get("theme");if(t!=="constat"&&t!=="native"){t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});}}catch(e){}d.setAttribute("data-theme",t==="native"?"native":"constat");})();`;
