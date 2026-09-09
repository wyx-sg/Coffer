import { afterEach, describe, expect, it } from "vitest";
import { getCofferBaseUrl, getCofferToken, setCofferToken } from "./auth";

// In production the daemon serves this bundle, so the API is same-origin and
// the token comes from localStorage (put there by the one-time-code exchange
// in webSession.ts). The injected globals are the Vite dev server's path —
// :5173 is not the daemon, so the dev plugin supplies its origin and token.
// These tests pin that read precedence.

const w = window as unknown as Record<string, unknown>;

afterEach(() => {
  delete w.__COFFER_TOKEN__;
  delete w.__COFFER_BASE_URL__;
  localStorage.clear();
});

describe("getCofferToken", () => {
  it("prefers the dev-injected global over localStorage", () => {
    localStorage.setItem("coffer.token", "ls-token");
    w.__COFFER_TOKEN__ = "dev-token";
    expect(getCofferToken()).toBe("dev-token");
  });

  it("reads the token the code exchange stored", () => {
    localStorage.setItem("coffer.token", "ls-token");
    expect(getCofferToken()).toBe("ls-token");
  });

  it("returns null when neither is present", () => {
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

describe("setCofferToken", () => {
  it("writes then clears the stored token", () => {
    setCofferToken("abc");
    expect(localStorage.getItem("coffer.token")).toBe("abc");
    setCofferToken(null);
    expect(localStorage.getItem("coffer.token")).toBeNull();
  });
});
