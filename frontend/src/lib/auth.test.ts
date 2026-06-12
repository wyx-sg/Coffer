import { afterEach, describe, expect, it } from "vitest";
import {
  getCofferBaseUrl,
  getCofferToken,
  setCofferToken,
  setDaemonConnection,
} from "./auth";

// The desktop app authenticates by having the Tauri shell inject
// window.__COFFER_TOKEN__ / __COFFER_BASE_URL__ into the WebView. That
// production path has no e2e (the browser suite injects via localStorage),
// so these unit tests pin the read precedence: injected globals win, with
// localStorage / Vite env / default as the dev fallbacks.

const w = window as unknown as Record<string, unknown>;

afterEach(() => {
  delete w.__COFFER_TOKEN__;
  delete w.__COFFER_BASE_URL__;
  localStorage.clear();
});

describe("getCofferToken", () => {
  it("prefers the Tauri-injected global over localStorage", () => {
    localStorage.setItem("coffer.token", "ls-token");
    w.__COFFER_TOKEN__ = "tauri-token";
    expect(getCofferToken()).toBe("tauri-token");
  });

  it("falls back to localStorage in dev when no global is injected", () => {
    localStorage.setItem("coffer.token", "ls-token");
    expect(getCofferToken()).toBe("ls-token");
  });

  it("returns null when neither is present", () => {
    expect(getCofferToken()).toBeNull();
  });
});

describe("getCofferBaseUrl", () => {
  it("prefers the Tauri-injected base URL", () => {
    w.__COFFER_BASE_URL__ = "http://127.0.0.1:18000/api/v1";
    expect(getCofferBaseUrl()).toBe("http://127.0.0.1:18000/api/v1");
  });

  it("falls back to a loopback default when nothing is injected", () => {
    // No Tauri global and (in the test env) no VITE_COFFER_BASE_URL.
    expect(getCofferBaseUrl()).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/api\/v1$/);
  });
});

describe("setDaemonConnection", () => {
  it("overwrites the injected globals so reads pick up the new daemon", () => {
    // Simulate the launch-time injection, then a daemon restart that minted
    // a new token (the daemon regenerates its token on every start).
    w.__COFFER_BASE_URL__ = "http://127.0.0.1:18000/api/v1";
    w.__COFFER_TOKEN__ = "stale-token";
    setDaemonConnection("http://127.0.0.1:18042/api/v1", "fresh-token");
    expect(getCofferBaseUrl()).toBe("http://127.0.0.1:18042/api/v1");
    expect(getCofferToken()).toBe("fresh-token");
  });
});

describe("setCofferToken", () => {
  it("writes then clears the dev localStorage token", () => {
    setCofferToken("abc");
    expect(localStorage.getItem("coffer.token")).toBe("abc");
    setCofferToken(null);
    expect(localStorage.getItem("coffer.token")).toBeNull();
  });
});
