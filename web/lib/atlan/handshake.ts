/**
 * Embedded handshake between the Atlan host page and a Constat /embed/* view.
 *
 * Rules, all enforced here and tested in tests/unit/handshake.test.ts:
 *   1. A message whose origin is not in allowedOrigins is ignored. Not
 *      logged, not answered, not parsed beyond the origin check.
 *   2. Every postMessage we send names an explicit targetOrigin. Never "*".
 *   3. The JWT lives in memory only (lib/api.ts setAuthToken). It is never
 *      written to storage, cookies or the URL.
 *   4. The host may refresh the token with atlan:token at any time.
 *
 * Protocol (type field on a plain object):
 *   constat:ready   embed -> host   { type, version }
 *   atlan:init      host  -> embed  { type, token, user, page, theme? }
 *   constat:ack     embed -> host   { type, view }
 *   atlan:token     host  -> embed  { type, token }
 *   atlan:theme     host  -> embed  { type, theme }
 */
import { setAuthToken } from "@/lib/api";
import { isTheme, type Theme } from "@/lib/theme";

export const HANDSHAKE_VERSION = "1";

export interface AtlanUser {
  id: string;
  email: string;
  name?: string;
  role?: "reviewer" | "owner" | "admin";
}

export interface AtlanPageContext {
  /** Where in Atlan the embed is rendered, e.g. "sidebar" or "asset-profile". */
  location: string;
  /** The Atlan asset in view, when there is one (a glossary term for a claim). */
  assetGuid?: string;
  assetQualifiedName?: string;
  tenant?: string;
}

export interface AtlanInitMessage {
  type: "atlan:init";
  token: string;
  user: AtlanUser;
  page: AtlanPageContext;
  theme?: Theme;
}

export interface AtlanTokenMessage {
  type: "atlan:token";
  token: string;
}

export interface AtlanThemeMessage {
  type: "atlan:theme";
  theme: Theme;
}

export type HostMessage = AtlanInitMessage | AtlanTokenMessage | AtlanThemeMessage;

export interface HandshakeOptions {
  /** Exact origins, or wildcard subdomains as "https://*.atlan.com". */
  allowedOrigins: string[];
  /** Name of the embedded view, echoed in constat:ack. */
  view?: string;
  onInit?: (msg: AtlanInitMessage, origin: string) => void;
  onToken?: (token: string) => void;
  onTheme?: (theme: Theme) => void;
  /** Injected in tests; defaults to window. */
  win?: Window;
}

export interface Handshake {
  stop(): void;
  /** Origin of the host that completed atlan:init, once it has. */
  readonly hostOrigin: string | null;
}

/** Parse NEXT_PUBLIC_ATLAN_ORIGINS (space or comma separated). */
export function originsFromEnv(value: string | undefined): string[] {
  return (value ?? "")
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * True when origin matches one of the allowed patterns. A pattern is either
 * an exact origin or "scheme://*.host" meaning any single-label-or-deeper
 * subdomain of host over that scheme. "null" and "*" never match.
 */
export function originAllowed(origin: string, allowed: readonly string[]): boolean {
  if (!origin || origin === "null") return false;
  let url: URL;
  try {
    url = new URL(origin);
  } catch {
    return false;
  }
  if (url.origin !== origin) return false;
  for (const pattern of allowed) {
    if (pattern === "*" || !pattern) continue;
    if (pattern === origin) return true;
    const m = /^(https?):\/\/\*\.([^/:*]+)(?::(\d+))?$/.exec(pattern);
    if (!m) continue;
    const [, scheme, host, port] = m;
    if (url.protocol !== `${scheme}:`) continue;
    if (port && url.port !== port) continue;
    if (!port && url.port) continue;
    if (url.hostname.endsWith(`.${host}`) && url.hostname.length > host.length + 1) return true;
  }
  return false;
}

function isHostMessage(data: unknown): data is HostMessage {
  if (!data || typeof data !== "object") return false;
  const t = (data as { type?: unknown }).type;
  if (t === "atlan:init") {
    const d = data as Partial<AtlanInitMessage>;
    return typeof d.token === "string" && !!d.user && typeof d.user === "object" && !!d.page && typeof d.page === "object";
  }
  if (t === "atlan:token") return typeof (data as Partial<AtlanTokenMessage>).token === "string";
  if (t === "atlan:theme") return isTheme((data as Partial<AtlanThemeMessage>).theme);
  return false;
}

function announceTheme(win: Window, theme: Theme) {
  win.dispatchEvent(new CustomEvent("constat:theme", { detail: theme }));
}

/**
 * Start listening for the host. Safe to call when not embedded: it then
 * does nothing except return a no-op stop(). Call once per embedded page.
 */
export function startHandshake(opts: HandshakeOptions): Handshake {
  const win = opts.win ?? (typeof window !== "undefined" ? window : undefined);
  const allowed = opts.allowedOrigins.filter(Boolean);
  let hostOrigin: string | null = null;

  if (!win || win.parent === win || allowed.length === 0) {
    return { stop() {}, get hostOrigin() { return hostOrigin; } };
  }

  const parent = win.parent;

  const listener = (event: MessageEvent) => {
    // Rule 1: the origin check happens before anything else.
    if (!originAllowed(event.origin, allowed)) return;
    // Rule 1b: only the window that frames us may talk to us; a sibling frame
    // on an allowed origin cannot swap the token.
    if (event.source !== parent) return;
    if (!isHostMessage(event.data)) return;
    const msg = event.data;

    if (msg.type === "atlan:init") {
      // Rule 4: the first host wins; a later init from another origin is ignored.
      if (hostOrigin && event.origin !== hostOrigin) return;
      hostOrigin = event.origin;
      setAuthToken(msg.token); // Rule 3: memory only
      if (msg.theme) announceTheme(win, msg.theme);
      opts.onInit?.(msg, event.origin);
      // Rule 2: reply only to the origin that initialised us.
      parent.postMessage({ type: "constat:ack", view: opts.view ?? null, version: HANDSHAKE_VERSION }, event.origin);
      return;
    }
    if (msg.type === "atlan:token") {
      if (hostOrigin && event.origin !== hostOrigin) return;
      setAuthToken(msg.token);
      opts.onToken?.(msg.token);
      return;
    }
    if (msg.type === "atlan:theme") {
      if (hostOrigin && event.origin !== hostOrigin) return;
      announceTheme(win, msg.theme);
      opts.onTheme?.(msg.theme);
    }
  };

  win.addEventListener("message", listener);

  // Rule 2: constat:ready goes only to concrete allowed origins. A wildcard
  // entry cannot be a targetOrigin, so a host behind one simply sends
  // atlan:init first and we acknowledge it to its exact origin.
  for (const origin of allowed) {
    if (origin.includes("*")) continue;
    try {
      parent.postMessage({ type: "constat:ready", version: HANDSHAKE_VERSION }, origin);
    } catch {
      // an invalid origin string throws; skip it rather than fall back to "*"
    }
  }

  return {
    stop() {
      win.removeEventListener("message", listener);
      setAuthToken(null);
    },
    get hostOrigin() {
      return hostOrigin;
    },
  };
}
