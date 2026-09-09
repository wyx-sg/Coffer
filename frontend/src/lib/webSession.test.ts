import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { consumeSignInCode, readCodeFromFragment } from "./webSession";
import { getCofferToken } from "./auth";

const w = window as unknown as Record<string, unknown>;

beforeEach(() => {
  w.__COFFER_BASE_URL__ = "http://127.0.0.1:18000/api/v1";
});

afterEach(() => {
  delete w.__COFFER_BASE_URL__;
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("readCodeFromFragment", () => {
  it("pulls the code out of a fragment", () => {
    expect(readCodeFromFragment("#code=abc123")).toBe("abc123");
  });

  it("tolerates other fragment params", () => {
    expect(readCodeFromFragment("#foo=1&code=abc123")).toBe("abc123");
  });

  it("returns null for an empty or unrelated fragment", () => {
    expect(readCodeFromFragment("")).toBeNull();
    expect(readCodeFromFragment("#")).toBeNull();
    expect(readCodeFromFragment("#section-two")).toBeNull();
    expect(readCodeFromFragment("#code=")).toBeNull();
  });
});

describe("consumeSignInCode", () => {
  it("exchanges the code for a token and stores it", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ token: "fresh-token" }), { status: 200 }));
    const replaceHash = vi.fn();

    const ok = await consumeSignInCode({ hash: "#code=abc123" }, replaceHash);

    expect(ok).toBe(true);
    expect(getCofferToken()).toBe("fresh-token");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:18000/api/v1/daemon/web-session");
    expect(JSON.parse(init!.body as string)).toEqual({ code: "abc123" });
  });

  it("strips the code from the address bar before exchanging it", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ token: "t" }), { status: 200 }),
    );
    const replaceHash = vi.fn();

    await consumeSignInCode({ hash: "#code=abc123" }, replaceHash);

    expect(replaceHash).toHaveBeenCalledTimes(1);
    expect(replaceHash.mock.calls[0][0]).not.toContain("abc123");
  });

  it("does nothing when there is no code", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const replaceHash = vi.fn();

    expect(await consumeSignInCode({ hash: "" }, replaceHash)).toBe(false);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(replaceHash).not.toHaveBeenCalled();
  });

  it("stores nothing when the daemon rejects a spent code", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    expect(await consumeSignInCode({ hash: "#code=spent" }, vi.fn())).toBe(false);
    expect(getCofferToken()).toBeNull();
  });

  it("survives the daemon being unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("connection refused"));
    const replaceHash = vi.fn();

    // Must resolve false rather than reject — main.tsx awaits this before the
    // first render, so a throw here would be a blank page.
    expect(await consumeSignInCode({ hash: "#code=abc" }, replaceHash)).toBe(false);
    // ...and the code is still scrubbed from the URL.
    expect(replaceHash).toHaveBeenCalledTimes(1);
  });
});
