"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import type { Theme } from "@/lib/theme";
import { HANDSHAKE_VERSION } from "@/lib/atlan/handshake";

/**
 * Stands in for the Atlan host page until a tenant exists. It iframes
 * /embed/review, fetches a dev-signed JWT, posts atlan:init with a fake user
 * and page context, lets you flip the theme, and logs every message that
 * comes back from the embed. All postMessage calls name the exact origin.
 */
const FAKE_USER = { id: "usr_dev_001", email: "fde@atlan.com", name: "Dev FDE", role: "reviewer" as const };
const FAKE_PAGE = {
  location: "sidebar",
  assetGuid: "guid-security-claims-glossary",
  assetQualifiedName: "default/glossary/security-claims",
  tenant: "dev-tenant",
};

type LogLine = { at: string; dir: "in" | "out"; text: string };

export function AtlanShell() {
  const frame = React.useRef<HTMLIFrameElement>(null);
  const [theme, setTheme] = React.useState<Theme>("native");
  const [view, setView] = React.useState("review");
  const [log, setLog] = React.useState<LogLine[]>([]);
  const [token, setToken] = React.useState<string | null>(null);
  const origin = typeof window !== "undefined" ? window.location.origin : "";

  const push = React.useCallback((dir: LogLine["dir"], text: string) => {
    setLog((l) => [{ at: new Date().toLocaleTimeString(), dir, text }, ...l].slice(0, 40));
  }, []);

  const post = React.useCallback(
    (msg: Record<string, unknown>) => {
      const w = frame.current?.contentWindow;
      if (!w) return;
      w.postMessage(msg, origin);
      push("out", JSON.stringify({ ...msg, token: msg.token ? "<jwt>" : undefined }));
    },
    [origin, push],
  );

  // Fetch a dev JWT once; it never leaves memory on this page either.
  React.useEffect(() => {
    fetch("/api/dev/token?email=fde@atlan.com&role=reviewer")
      .then((r) => r.json())
      .then((j: { token: string }) => setToken(j.token))
      .catch(() => push("in", "token fetch failed"));
  }, [push]);

  const sendInit = React.useCallback(() => {
    if (!token) return;
    post({ type: "atlan:init", token, user: FAKE_USER, page: FAKE_PAGE, theme });
  }, [post, token, theme]);

  React.useEffect(() => {
    function onMessage(e: MessageEvent) {
      if (e.origin !== origin) return; // the embed is same-origin here
      const data = e.data as { type?: string } | null;
      if (!data || typeof data.type !== "string" || !data.type.startsWith("constat:")) return;
      push("in", JSON.stringify(data));
      if (data.type === "constat:ready") sendInit();
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [origin, push, sendInit]);

  // If the frame was ready before the token arrived, init once we have it.
  React.useEffect(() => {
    if (token) sendInit();
  }, [token, sendInit]);

  function flipTheme() {
    const next: Theme = theme === "native" ? "constat" : "native";
    setTheme(next);
    post({ type: "atlan:theme", theme: next });
  }

  return (
    <div className="grid min-h-dvh grid-rows-[auto_1fr] bg-muted text-foreground" data-theme="native">
      <header className="flex flex-wrap items-center gap-3 border-b bg-background px-4 py-2">
        <span className="font-semibold">Atlan shell simulator</span>
        <span className="eyebrow">dev only, handshake v{HANDSHAKE_VERSION}</span>
        <label className="ml-auto flex items-center gap-2 text-sm">
          View
          <select className="rounded-md border bg-background px-2 py-1" value={view} onChange={(e) => setView(e.target.value)}>
            <option value="review">review</option>
            <option value="inbox">inbox</option>
            <option value="claims">claims</option>
            <option value="claims/freshness">claims/freshness</option>
            <option value="metrics">metrics</option>
          </select>
        </label>
        <Button size="sm" variant="outline" onClick={flipTheme} data-testid="shell-theme">
          Theme: {theme}
        </Button>
        <Button size="sm" variant="outline" onClick={() => post({ type: "atlan:token", token: token ?? "" })} disabled={!token}>
          Refresh token
        </Button>
        <Button size="sm" onClick={sendInit} disabled={!token} data-testid="shell-init">
          Re-send init
        </Button>
      </header>
      <div className="grid gap-3 p-3 lg:grid-cols-[1fr_320px]">
        <div className="min-h-[70vh] overflow-hidden rounded-lg border bg-background">
          <iframe
            ref={frame}
            title="Constat embedded view"
            src={`/embed/${view}?theme=${theme}`}
            className="h-full min-h-[70vh] w-full"
            data-testid="shell-frame"
          />
        </div>
        <aside className="rounded-lg border bg-background p-3">
          <p className="eyebrow mb-2">Messages</p>
          <ol className="space-y-1 font-mono text-[11px]" data-testid="shell-log">
            {log.map((l, i) => (
              <li key={i} className="break-all">
                <span className="text-muted-foreground">{l.at} </span>
                <span className={l.dir === "in" ? "text-status-ok" : "text-status-info"}>{l.dir === "in" ? "<-" : "->"} </span>
                {l.text}
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  );
}
