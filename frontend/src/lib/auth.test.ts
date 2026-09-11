import { afterEach, describe, expect, it } from "vitest";
import { getCofferBaseUrl, getCofferToken } from "./auth";

// The token reaches the page in the page: the daemon injects
// `window.__COFFER_TOKEN__` into the index.html it serves, and the Vite dev
// server's plugin injects the same global (plus a base URL, since :5173 is not
// the daemon). Nothing is read from storage — a persisted token outlives the
// daemon that minted it, which is precisely the failure this replaced.

const w = window as unknown as Record<string, unknown>;

afterEach(() => {
  delete w.__COFFER_TOKEN__;
  delete w.__COFFER_BASE_URL__;
  localStorage.clear();
});

describe("getCofferToken", () => {
  it("reads the token injected into the served document", () => {
    w.__COFFER_TOKEN__ = "live-token";
    expect(getCofferToken()).toBe("live-token");
  });

  it("returns null when the page carries no token", () => {
    expect(getCofferToken()).toBeNull();
  });

  it("ignores a token left in localStorage by an older build", () => {
    localStorage.setItem("coffer.token", "stale-token");
    expect(getCofferToken()).toBeNull();
  });
});

describe("getCofferBaseUrl", () => {
  it("prefers the dev-injected base URL", () => {
    w.__COFFER_BASE_URL__ = "http://127.0.0.1:18000/api/v1";
    expect(getCofferBaseUrl()).toBe("http://127.0.0.1:18000/api/v1");
  });

  it("falls back to this page's own origin — the daemon serves it", () => {
    expect(getCofferBaseUrl()).toBe(`${window.location.origin}/api/v1`);
  });
});
