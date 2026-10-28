"use client";

import * as React from "react";

/**
 * Screens are rendered twice: under the app chrome at /review etc, and bare
 * at /embed/review etc inside Atlan. Links inside a screen go through href()
 * so they stay inside whichever surface the user is on.
 */
export interface EmbedContextValue {
  embedded: boolean;
  href: (path: string) => string;
}

export const EmbedContext = React.createContext<EmbedContextValue>({
  embedded: false,
  href: (p) => p,
});

export function useEmbed(): EmbedContextValue {
  return React.useContext(EmbedContext);
}

export function embedHref(path: string): string {
  if (path.startsWith("/embed/")) return path;
  return `/embed${path}`;
}
