// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { originAllowed, startHandshake, type AtlanInitMessage } from "@/lib/atlan/handshake";

const ALLOWED = ["https://tenant.atlan.com", "https://*.atlan.com", "http://localhost:3000"];

function fakeWindow() {
  const target = new EventTarget();
  const parentPost = vi.fn();
  const win = {
    parent: { postMessage: parentPost },
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
    dispatchEvent: target.dispatchEvent.bind(target),
  } as unknown as Window;
  const deliver = (origin: string, data: unknown) => {
    target.dispatchEvent(new MessageEvent("message", { origin, data }));
  };
  return { win, parentPost, deliver };
}

const init: AtlanInitMessage = {
  type: "atlan:init",
  token: "jwt.token.value",
  user: { id: "u1", email: "fde@atlan.com", role: "reviewer" },
  page: { location: "sidebar", tenant: "tenant" },
  theme: "native",
};

describe("originAllowed", () => {
  it("accepts exact origins and wildcard subdomains only", () => {
    expect(originAllowed("https://tenant.atlan.com", ALLOWED)).toBe(true);
    expect(originAllowed("https://other.atlan.com", ALLOWED)).toBe(true);
    expect(originAllowed("https://deep.other.atlan.com", ALLOWED)).toBe(true);
    expect(originAllowed("http://localhost:3000", ALLOWED)).toBe(true);
  });
  it("rejects look-alikes, wrong schemes, null and wildcards", () => {
    expect(originAllowed("https://atlan.com", ALLOWED)).toBe(false);
    expect(originAllowed("https://evil-atlan.com", ALLOWED)).toBe(false);
    expect(originAllowed("https://atlan.com.evil.example", ALLOWED)).toBe(false);
    expect(originAllowed("http://tenant.atlan.com", ALLOWED)).toBe(false);
    expect(originAllowed("http://localhost:3001", ALLOWED)).toBe(false);
    expect(originAllowed("null", ALLOWED)).toBe(false);
    expect(originAllowed("https://anything.example", ["*"])).toBe(false);
  });
});

describe("startHandshake", () => {
  let api: typeof import("@/lib/api");
  beforeEach(async () => {
    api = await import("@/lib/api");
    api.setAuthToken(null);
  });
  afterEach(() => {
    api.setAuthToken(null);
  });

  it("ignores an init message from a wrong origin", () => {
    const { win, parentPost, deliver } = fakeWindow();
    const onInit = vi.fn();
    const hs = startHandshake({ allowedOrigins: ALLOWED, win, onInit, view: "review" });
    parentPost.mockClear();

    deliver("https://evil.example", init);

    expect(onInit).not.toHaveBeenCalled();
    expect(parentPost).not.toHaveBeenCalled();
    expect(hs.hostOrigin).toBeNull();
    hs.stop();
  });

  it("accepts init from an allowed origin and acks that exact origin", () => {
    const { win, parentPost, deliver } = fakeWindow();
    const onInit = vi.fn();
    const themes: string[] = [];
    win.addEventListener("constat:theme", (e) => themes.push((e as CustomEvent<string>).detail));
    const hs = startHandshake({ allowedOrigins: ALLOWED, win, onInit, view: "review" });

    // constat:ready went only to concrete origins, never "*"
    const readyTargets = parentPost.mock.calls.map((c) => c[1]);
    expect(readyTargets).toEqual(["https://tenant.atlan.com", "http://localhost:3000"]);
    expect(readyTargets).not.toContain("*");
    parentPost.mockClear();

    deliver("https://other.atlan.com", init);

    expect(onInit).toHaveBeenCalledTimes(1);
    expect(hs.hostOrigin).toBe("https://other.atlan.com");
    expect(parentPost).toHaveBeenCalledWith(
      expect.objectContaining({ type: "constat:ack", view: "review" }),
      "https://other.atlan.com",
    );
    expect(themes).toEqual(["native"]);
    hs.stop();
  });

  it("ignores a token refresh from any origin other than the host", () => {
    const { win, deliver } = fakeWindow();
    const onToken = vi.fn();
    const hs = startHandshake({ allowedOrigins: ALLOWED, win, onToken });
    deliver("https://tenant.atlan.com", init);
    deliver("https://other.atlan.com", { type: "atlan:token", token: "stolen" });
    expect(onToken).not.toHaveBeenCalled();
    deliver("https://tenant.atlan.com", { type: "atlan:token", token: "fresh" });
    expect(onToken).toHaveBeenCalledWith("fresh");
    hs.stop();
  });

  it("never touches storage with the token", () => {
    const { win, deliver } = fakeWindow();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const hs = startHandshake({ allowedOrigins: ALLOWED, win });
    deliver("https://tenant.atlan.com", init);
    const stored = setItem.mock.calls.flat().join(" ");
    expect(stored).not.toContain("jwt.token.value");
    expect(document.cookie).not.toContain("jwt.token.value");
    hs.stop();
    setItem.mockRestore();
  });

  it("does nothing when not embedded", () => {
    const post = vi.fn();
    const win = { parent: null as unknown, addEventListener: vi.fn(), postMessage: post } as unknown as Window;
    (win as { parent: unknown }).parent = win;
    const hs = startHandshake({ allowedOrigins: ALLOWED, win });
    expect(win.addEventListener).not.toHaveBeenCalled();
    expect(hs.hostOrigin).toBeNull();
    hs.stop();
  });
});
