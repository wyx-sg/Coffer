// frontend/src/kinds/knowledge/api.test.ts
//
// Exercises the scope / entry / lane fetch helpers of the one `knowledge` kind.
// `global` and `project-<ULID>` auto-provision (only a NAMED collection is
// created by hand); entries are written directly (no LLM). We stub the global
// fetch so each test can verify URL + method + headers + body.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import {
  addEntry,
  clearEntries,
  deleteConsolidationLog,
  deleteEntry,
  deleteHandoffBranch,
  deleteKnowledgeRules,
  getEntry,
  getConsolidationLog,
  getKnowledgeHandoff,
  getKnowledgeRules,
  getScope,
  getScopeMetrics,
  listEntries,
  listScopes,
  mergeScopes,
  mergeScanScopes,
  recall,
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

describe("lane deletes", () => {
  test("deleteHandoffBranch DELETEs /handoff/<branch> (branch encoded)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteHandoffBranch("prefs", "feat/x");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/handoff/feat%2Fx`);
    expect(init?.method).toBe("DELETE");
  });

  test("deleteKnowledgeRules DELETEs /rules", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteKnowledgeRules("prefs");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/rules`);
    expect(init?.method).toBe("DELETE");
  });

  test("deleteConsolidationLog DELETEs /consolidation-log", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteConsolidationLog("prefs");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/consolidation-log`);
    expect(init?.method).toBe("DELETE");
  });

  test("throws a typed ApiError on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_NOT_FOUND", message: "no such file" } }),
    );
    const err = await deleteHandoffBranch("prefs", "ghost").catch((e) => e);
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

describe("recall", () => {
  test("POSTs query + top_k (no mode) to /recall and returns hits", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        hits: [{ id: "m-1", text: "uses tabs", score: 0.92, source: "global", time: "t" }],
      }),
    );

    const out = await recall("prefs", "tabs", { topK: 3 });
    expect(out.hits).toHaveLength(1);
    expect(out.hits[0].text).toBe("uses tabs");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/prefs/recall`);
    // "One query → one answer": the request carries no mode.
    expect(JSON.parse(init!.body as string)).toEqual({ query: "tabs", top_k: 3 });
  });

  test("defaults top_k to 5 when omitted", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ hits: [] }));
    await recall("prefs", "anything");
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({
      query: "anything",
      top_k: 5,
    });
  });
});

describe("getScopeMetrics", () => {
  test("returns the metrics payload as-is", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ entry_count: 5, disk_bytes: 4096 }));
    const out = await getScopeMetrics("prefs");
    expect(out).toEqual({ entry_count: 5, disk_bytes: 4096 });
  });
});

describe("getKnowledgeRules", () => {
  test("GETs /knowledge/<scope>/rules and returns the text payload", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ text: "always lint" }));
    const out = await getKnowledgeRules("prefs");
    expect(out.text).toBe("always lint");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/knowledge/prefs/rules`);
    expect((fetchMock.mock.calls[0][1] as RequestInit | undefined)?.method).toBeUndefined();
  });

  test("returns null text when the scope has no rules", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ text: null }));
    expect((await getKnowledgeRules("prefs")).text).toBeNull();
  });

  test("throws a typed ApiError on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_NOT_FOUND", message: "no scope" } }),
    );
    const err = await getKnowledgeRules("ghost").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_NOT_FOUND");
  });
});

describe("getKnowledgeHandoff", () => {
  test("GETs /knowledge/<scope>/handoff and returns the scenes list", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        scenes: [
          {
            branch: "feat/x",
            text: "wip",
            updated_at: "2026-06-22T00:00:00Z",
            path: "/p/feat-x.md",
            folder_path: "/p",
          },
        ],
      }),
    );
    const out = await getKnowledgeHandoff("prefs");
    expect(out.scenes[0].branch).toBe("feat/x");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/knowledge/prefs/handoff`);
  });
});

describe("getConsolidationLog", () => {
  test("GETs /knowledge/<scope>/consolidation-log and returns the text + path", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ text: "consolidated", path: "/p/log.md", folder_path: "/p" }));
    const out = await getConsolidationLog("prefs");
    expect(out.text).toBe("consolidated");
    expect(out.path).toBe("/p/log.md");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/knowledge/prefs/consolidation-log`);
  });

  test("returns null text when absent (still 200)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({ text: null, path: "/p/log.md", folder_path: "/p" }),
    );
    expect((await getConsolidationLog("prefs")).text).toBeNull();
  });
});

describe("mergeScanScopes", () => {
  test("POSTs /knowledge/merge_scan and returns the proposals", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ engine: "no_model", truncated: false, proposals: [] }));
    const out = await mergeScanScopes();
    expect(out.engine).toBe("no_model");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/merge_scan`);
    expect(init?.method).toBe("POST");
  });
});

describe("mergeScopes", () => {
  test("POSTs source/target and defaults organize to true", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        target: "project-a",
        merged_files: 2,
        label_moved: true,
        root_moved: false,
        aliases: ["b"],
        reorg_status: "no_model",
      }),
    );
    const out = await mergeScopes("project-b", "project-a");
    expect(out.aliases).toEqual(["b"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/merge`);
    expect(JSON.parse(String(init?.body))).toEqual({
      source: "project-b",
      target: "project-a",
      organize: true,
    });
  });

  test("surfaces the typed error envelope on a 400", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(400, { error: { code: "MEMORY_STORE_MERGE_INVALID", message: "same scope" } }),
    );
    await expect(mergeScopes("project-a", "project-a")).rejects.toMatchObject({
      code: "MEMORY_STORE_MERGE_INVALID",
    });
    expect(ApiError).toBeDefined();
  });
});
