// frontend/src/lib/api/call.test.ts
//
// The one hand-written request helper every non-generated api module rides on.
// We stub `globalThis.fetch` and pin the transport contract: the auth headers
// every request carries, JSON vs multipart bodies, 204 → undefined, and the
// `{error:{code,message,details}}` envelope → ApiError.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { call, enc } from "./call";
import { ApiError } from "./errors";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// The token reaches the page as an injected global (see lib/auth.ts); these
// tests set it the same way the daemon's served index.html does.
const w = window as unknown as Record<string, unknown>;

function lastInit(fetchMock: ReturnType<typeof vi.fn>): RequestInit {
  return fetchMock.mock.calls[0][1] as RequestInit;
}

describe("call", () => {
  beforeEach(() => {
    w.__COFFER_TOKEN__ = "secret-token";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    delete w.__COFFER_TOKEN__;
  });

  test("GETs by default, sending the token + ui actor and no Content-Type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const out = await call<{ ok: boolean }>("/things");
    expect(out).toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/things$/);
    expect(init.method).toBe("GET");
    const headers = init.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("secret-token");
    expect(headers["X-Coffer-Actor"]).toBe("ui");
    expect(headers["Content-Type"]).toBeUndefined();
    expect("body" in init).toBe(false);
  });

  test("sends an empty token header when no token is set", async () => {
    delete w.__COFFER_TOKEN__;
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await call("/things");
    expect((lastInit(fetchMock).headers as Record<string, string>)["X-Coffer-Token"]).toBe("");
  });

  test("JSON-encodes a body and sets Content-Type: application/json", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, { id: "x" }));
    vi.stubGlobal("fetch", fetchMock);

    await call("/things", { method: "POST", body: { name: "a", n: 1 } });

    const init = lastInit(fetchMock);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ name: "a", n: 1 }));
  });

  test("passes a FormData body through untouched with NO Content-Type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { path: "c/f.md" }));
    vi.stubGlobal("fetch", fetchMock);

    const form = new FormData();
    form.append("collection", "c");
    await call("/knowledge/upload", { method: "POST", body: form });

    const init = lastInit(fetchMock);
    expect(init.body).toBe(form);
    // The browser must write the multipart boundary itself; a preset
    // Content-Type would ship a body the daemon cannot parse.
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
    expect((init.headers as Record<string, string>)["X-Coffer-Actor"]).toBe("ui");
  });

  test("resolves a 204 to undefined without reading a body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(call<void>("/things/x", { method: "DELETE" })).resolves.toBeUndefined();
  });

  test("throws an ApiError carrying code, message and details from the envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(422, {
          error: { code: "INGEST_REJECTED", message: "too big", details: { reason: "size" } },
        }),
      ),
    );

    const err = await call("/things").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      code: "INGEST_REJECTED",
      message: "too big",
      envelopeMessage: "too big",
      details: { reason: "size" },
    });
  });

  test("falls back to INTERNAL_ERROR + status when the error body is not the envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("not json", { status: 500, headers: { "Content-Type": "text/plain" } }),
        ),
    );

    await expect(call("/things")).rejects.toMatchObject({
      code: "INTERNAL_ERROR",
      message: "request failed: 500",
      details: undefined,
    });
  });
});

describe("enc", () => {
  test("is encodeURIComponent", () => {
    expect(enc("a b/c?d")).toBe("a%20b%2Fc%3Fd");
  });
});
