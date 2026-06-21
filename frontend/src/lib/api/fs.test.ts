// frontend/src/lib/api/fs.test.ts
//
// The web folder-picker browses the filesystem through the loopback daemon's
// /fs/browse endpoint. We stub `globalThis.fetch` and assert the request
// shaping (URL + auth headers + query encoding) and the success / error
// envelope handling.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fsApi } from "./fs";
import { ApiError } from "./errors";
import { setCofferToken } from "../auth";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("fsApi.browse", () => {
  beforeEach(() => {
    setCofferToken("secret-token");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setCofferToken(null);
  });

  test("GETs /fs/browse with no query when path is omitted, sending auth headers", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { path: "/", parent: null, entries: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const out = await fsApi.browse();
    expect(out).toEqual({ path: "/", parent: null, entries: [] });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/fs\/browse$/);
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("secret-token");
    expect(headers["X-Coffer-Actor"]).toBe("ui");
  });

  test("URL-encodes the path into the query string", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        path: "/home/u/my dir",
        parent: "/home/u",
        entries: [{ name: "child", path: "/home/u/my dir/child" }],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const out = await fsApi.browse("/home/u/my dir");
    expect(out.entries).toHaveLength(1);
    expect(out.parent).toBe("/home/u");

    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("?path=");
    expect(calledUrl).toContain(encodeURIComponent("/home/u/my dir"));
    // The raw space must not appear unencoded.
    expect(calledUrl).not.toContain("my dir");
  });

  test("sends an empty token header when no token is set", async () => {
    setCofferToken(null);
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { path: "/", parent: null, entries: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await fsApi.browse();
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("");
  });

  test("throws an ApiError carrying the server envelope on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(403, { error: { code: "FORBIDDEN", message: "no access" } }),
        ),
    );

    await expect(fsApi.browse("/etc")).rejects.toMatchObject({
      code: "FORBIDDEN",
      message: "no access",
    });
    await expect(fsApi.browse("/etc")).rejects.toBeInstanceOf(ApiError);
  });

  test("falls back to a synthetic error when the error body is unparseable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("not json", { status: 500, headers: { "Content-Type": "text/plain" } }),
        ),
    );

    await expect(fsApi.browse()).rejects.toMatchObject({
      code: "INTERNAL_ERROR",
      message: expect.stringContaining("500"),
    });
  });
});

describe("fsApi.pickFile / saveFile (native file dialogs, FR-042)", () => {
  beforeEach(() => setCofferToken("secret-token"));
  afterEach(() => {
    vi.unstubAllGlobals();
    setCofferToken(null);
  });

  test("pickFile POSTs /fs/pick-file with the start dir and auth headers", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { available: true, path: "/Users/me/coffer.key" }));
    vi.stubGlobal("fetch", fetchMock);

    const out = await fsApi.pickFile("/Users/me");
    expect(out).toEqual({ available: true, path: "/Users/me/coffer.key" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/fs\/pick-file$/);
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ start: "/Users/me" });
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("secret-token");
    expect(headers["X-Coffer-Actor"]).toBe("ui");
  });

  test("pickFile sends start:null when omitted", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { available: false, path: null }));
    vi.stubGlobal("fetch", fetchMock);

    await fsApi.pickFile();
    expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toEqual({
      start: null,
    });
  });

  test("saveFile POSTs /fs/save-file with the suggested name + start", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { available: true, path: "/Users/me/out.key" }));
    vi.stubGlobal("fetch", fetchMock);

    const out = await fsApi.saveFile("coffer-master.key", "/Users/me");
    expect(out).toEqual({ available: true, path: "/Users/me/out.key" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/fs\/save-file$/);
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      suggested_name: "coffer-master.key",
      start: "/Users/me",
    });
  });

  test("saveFile defaults suggested_name + start to null", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { available: true, path: null }));
    vi.stubGlobal("fetch", fetchMock);

    await fsApi.saveFile();
    expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toEqual({
      suggested_name: null,
      start: null,
    });
  });

  test("pickFile throws an ApiError carrying the server envelope on a non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(401, { error: { code: "UNAUTHENTICATED", message: "nope" } }),
        ),
    );
    await expect(fsApi.pickFile()).rejects.toMatchObject({ code: "UNAUTHENTICATED" });
    await expect(fsApi.pickFile()).rejects.toBeInstanceOf(ApiError);
  });
});
