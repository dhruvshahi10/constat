"use client";

import * as React from "react";
import { EmbedContext, embedHref } from "@/lib/embed";
import { originsFromEnv, startHandshake, type AtlanInitMessage } from "@/lib/atlan/handshake";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { DegradationBanner } from "@/components/shell/degradation-banner";

/**
 * Chrome-less wrapper for /embed/[...view]. Starts the host handshake once,
 * exposes the embed link helper, and shows only what Atlan does not already
 * provide around the iframe: the degradation notice and a theme toggle.
 */
export function EmbedFrame({ view, children }: { view: string; children: React.ReactNode }) {
  const [host, setHost] = React.useState<AtlanInitMessage | null>(null);

  React.useEffect(() => {
    const allowed = [
      window.location.origin, // the dev shell at /dev/atlan-shell, same origin as 'self' in the CSP
      "https://*.atlan.com",
      ...originsFromEnv(process.env.NEXT_PUBLIC_ATLAN_ORIGINS),
    ];
    const hs = startHandshake({
      allowedOrigins: allowed,
      view,
      onInit: (msg) => setHost(msg),
    });
    return () => hs.stop();
  }, [view]);

  const value = React.useMemo(() => ({ embedded: true, href: embedHref }), []);

  return (
    <EmbedContext.Provider value={value}>
      <div className="min-h-dvh bg-background text-foreground" data-embedded="true" data-host-user={host?.user.email ?? ""}>
        <div className="flex items-center gap-2 px-4 pt-3">
          <div className="min-w-0 flex-1">
            <DegradationBanner compact />
          </div>
          <ThemeToggle />
        </div>
        <div className="px-4 py-4 sm:px-6">{children}</div>
      </div>
    </EmbedContext.Provider>
  );
}
