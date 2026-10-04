// frontend/src/lib/api/fs.test.ts
//
// The web folder-picker browses the filesystem through the loopback daemon's
// /fs/browse endpoint. We stub `globalThis.fetch` and assert what `fsApi`
// puts on the wire (URL, query encoding, body). The typed client's own
// behaviour (auth headers, error envelopes) is covered in client.test.ts.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { resetApiClient } from "./client";
import { fsApi } from "./fs";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** The `Request` the typed client handed to `fetch` on its `n`th call. */
function sent(fetchMock: ReturnType<typeof vi.fn>, n = 0): Request {
  return fetchMock.mock.calls[n][0] as Request;
}

beforeEach(() => {
  resetApiClient();
});
afterEach(() => {
  vi.unstubAllGlobals();
  resetApiClient();
});

describe("fsApi.browse", () => {
  test("GETs /fs/browse with no query when path is omitted", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { path: "/", parent: null, entries: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const out = await fsApi.browse();
    expect(out).toEqual({ path: "/", parent: null, entries: [] });

    const request = sent(fetchMock);
    expect(request.method).toBe("GET");
    expect(request.url).toMatch(/\/fs\/browse$/);
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

    const calledUrl = sent(fetchMock).url;
    expect(calledUrl).toContain("?path=");
    expect(new URL(calledUrl).searchParams.get("path")).toBe("/home/u/my dir");
    // The raw space must not appear unencoded.
    expect(calledUrl).not.toContain("my dir");
  });
});

describe("fsApi.open", () => {
  test("sends the editor only when one is given, and resolves with nothing on 204", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fsApi.open("/a/b.md")).resolves.toBeUndefined();
    await expect(fsApi.open("/a/b.md", "Cursor")).resolves.toBeUndefined();

    expect(await sent(fetchMock, 0).clone().json()).toEqual({ path: "/a/b.md" });
    expect(await sent(fetchMock, 1).clone().json()).toEqual({ path: "/a/b.md", with: "Cursor" });
  });
});
