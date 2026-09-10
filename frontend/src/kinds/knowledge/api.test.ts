// frontend/src/kinds/knowledge/api.test.ts
//
// Exercises the scope / note fetch helpers of the one `knowledge` kind.
// `global` and `project-<ULID>` auto-provision (only a NAMED collection is
// created by hand); notes are written directly (no LLM). We stub the global
// fetch so each test can verify URL + method + headers + body.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import {
  addEntry,
  clearEntries,
  deleteEntry,
  getEntry,
  getScope,
  getScopeMetrics,
  listEntries,
  listScopes,
  tidyScope,
} from "./api";

const BASE = "http://test-host/api/v1";

function okJson(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

function notOkJson(status: number, body: unknown): Response {
  return {
    ok: false,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

beforeEach(() => {
  (window as unknown as Record<string, unknown>).__COFFER_BASE_URL__ = BASE;
  (window as unknown as Record<string, unknown>).__COFFER_TOKEN__ = "test-token";
});

afterEach(() => {
  vi.restoreAllMocks();
  (window as unknown as Record<string, unknown>).__COFFER_BASE_URL__ = undefined;
  (window as unknown as Record<string, unknown>).__COFFER_TOKEN__ = undefined;
});

describe("listScopes", () => {
  test("GETs /knowledge and unwraps the scopes list", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ scopes: [] }));
    const out = await listScopes();
    expect(out.scopes).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/knowledge`);
  });
});

describe("getScope", () => {
  test("GETs a single scope with scope + project_id", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({ name: "global", scope: "global", project_id: "0".repeat(26) }),
    );
    const out = await getScope("global");
    expect(out.scope).toBe("global");
  });
});

describe("listEntries", () => {
  test("GETs /knowledge/<scope>/entries with paging params", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ entries: [], total: 0 }));

    const out = await listEntries("prefs", 25, 50);
    expect(out).toEqual({ entries: [], total: 0 });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/knowledge/prefs/entries?limit=25&offset=50`);
  });

  test("URL-encodes the scope name", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ entries: [], total: 0 }));
    await listEntries("scope with space");
    expect(fetchMock.mock.calls[0][0]).toContain("scope%20with%20space");
  });
});

describe("addEntry", () => {
  test("POSTs the entry fields to /entries", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ id: "m-1", title: "tabs", text: "uses tabs", actor: "user" }));

    const out = await addEntry("prefs", { text: "uses tabs", title: "tabs" });
    expect(out.id).toBe("m-1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/entries`);
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Actor"]).toBe("user");
    expect(JSON.parse(init!.body as string)).toEqual({
      text: "uses tabs",
      title: "tabs",
    });
  });

  test("throws a typed ApiError carrying the envelope code + message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(422, { error: { code: "MEMORY_REJECTED", message: "entry too long" } }),
    );
    const err = await addEntry("prefs", { text: "" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_REJECTED");
    expect((err as ApiError).message).toBe("entry too long");
  });

  test("falls back to INTERNAL_ERROR when the body is not a JSON envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
      text: async () => "boom",
    } as unknown as Response);
    const err = await addEntry("prefs", { text: "x" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("INTERNAL_ERROR");
  });
});

describe("deleteEntry", () => {
  test("DELETEs /knowledge/<scope>/entries/<id>", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteEntry("prefs", "m-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/entries/m-1`);
    expect(init?.method).toBe("DELETE");
  });

  test("throws a typed ApiError with the envelope code on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_NOT_FOUND", message: "no such entry" } }),
    );
    const err = await deleteEntry("prefs", "ghost").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_NOT_FOUND");
  });
});

describe("getEntry", () => {
  test("GETs /knowledge/<scope>/entries/<id> and returns the full entry", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ id: "m-1", title: "tabs", text: "uses tabs", actor: "user" }));
    const out = await getEntry("prefs", "m-1");
    expect(out.id).toBe("m-1");
    expect(out.text).toBe("uses tabs");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/entries/m-1`);
    expect(init?.method).toBeUndefined();
  });

  test("URL-encodes the scope name and entry id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ id: "x" }));
    await getEntry("scope with space", "a/b?c");
    expect(fetchMock.mock.calls[0][0]).toContain("scope%20with%20space");
    expect(fetchMock.mock.calls[0][0]).toContain("a%2Fb%3Fc");
  });
});

describe("clearEntries", () => {
  test("DELETEs /entries and returns the cleared count", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ cleared: 7 }));
    const n = await clearEntries("prefs");
    expect(n).toBe(7);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/entries`);
    expect(init?.method).toBe("DELETE");
  });
});

describe("getScopeMetrics", () => {
  test("returns the metrics payload as-is", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ entry_count: 5, disk_bytes: 4096 }));
    const out = await getScopeMetrics("prefs");
    expect(out).toEqual({ entry_count: 5, disk_bytes: 4096 });
  });
});

describe("tidyScope", () => {
  test("POSTs /knowledge/<scope>/organize — the manual tidy trigger", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ status: "no_model" }));
    const out = await tidyScope("prefs");
    expect(out.status).toBe("no_model");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/organize`);
    expect(init?.method).toBe("POST");
  });

  test("throws a typed ApiError on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_STORE_NOT_FOUND", message: "no scope" } }),
    );
    const err: unknown = await tidyScope("ghost").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_STORE_NOT_FOUND");
  });
});
