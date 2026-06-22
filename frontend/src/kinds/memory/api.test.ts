// frontend/src/kinds/memory/api.test.ts
//
// Exercises the redesigned memory fetch helpers (spec 007). Stores are
// auto-provisioned (no create); facts are written directly (no LLM). We stub
// the global fetch so each test can verify URL + method + headers + body.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import {
  addFact,
  clearFacts,
  deleteConsolidationLog,
  deleteFact,
  deleteHandoffBranch,
  deleteJournalPeriod,
  deleteMemoryRules,
  getFact,
  getMemoryConsolidationLog,
  getMemoryHandoff,
  getMemoryJournal,
  getMemoryRules,
  getMemoryStore,
  getMemoryStoreMetrics,
  listFacts,
  listMemoryStores,
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

describe("listMemoryStores", () => {
  test("GETs /memory_stores and unwraps the list", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ memory_stores: [] }));
    const out = await listMemoryStores();
    expect(out.memory_stores).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/memory_stores`);
  });
});

describe("getMemoryStore", () => {
  test("GETs a single store with scope + project_id", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({ name: "global", scope: "global", project_id: "0".repeat(26) }),
    );
    const out = await getMemoryStore("global");
    expect(out.scope).toBe("global");
  });
});

describe("listFacts", () => {
  test("GETs /memory_stores/<name>/facts with paging params", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ facts: [], total: 0 }));

    const out = await listFacts("prefs", 25, 50);
    expect(out).toEqual({ facts: [], total: 0 });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/memory_stores/prefs/facts?limit=25&offset=50`);
  });

  test("URL-encodes the store name", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ facts: [], total: 0 }));
    await listFacts("store with space");
    expect(fetchMock.mock.calls[0][0]).toContain("store%20with%20space");
  });
});

describe("addFact", () => {
  test("POSTs the fact fields to /facts", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ id: "m-1", title: "tabs", text: "uses tabs", actor: "user" }));

    const out = await addFact("prefs", { text: "uses tabs", title: "tabs" });
    expect(out.id).toBe("m-1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/facts`);
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
      notOkJson(422, { error: { code: "MEMORY_REJECTED", message: "fact too long" } }),
    );
    const err = await addFact("prefs", { text: "" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_REJECTED");
    expect((err as ApiError).message).toBe("fact too long");
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
    const err = await addFact("prefs", { text: "x" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("INTERNAL_ERROR");
  });
});

describe("deleteFact", () => {
  test("DELETEs /memory_stores/<store>/facts/<id>", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteFact("prefs", "m-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/facts/m-1`);
    expect(init?.method).toBe("DELETE");
  });

  test("throws a typed ApiError with the envelope code on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_NOT_FOUND", message: "no such fact" } }),
    );
    const err = await deleteFact("prefs", "ghost").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_NOT_FOUND");
  });
});

describe("lane deletes", () => {
  test("deleteJournalPeriod DELETEs /journal/<period> (period encoded)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteJournalPeriod("prefs", "2026-06");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/journal/2026-06`);
    expect(init?.method).toBe("DELETE");
  });

  test("deleteHandoffBranch DELETEs /handoff/<branch> (branch encoded)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteHandoffBranch("prefs", "feat/x");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/handoff/feat%2Fx`);
    expect(init?.method).toBe("DELETE");
  });

  test("deleteMemoryRules DELETEs /rules", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteMemoryRules("prefs");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/rules`);
    expect(init?.method).toBe("DELETE");
  });

  test("deleteConsolidationLog DELETEs /consolidation-log", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));
    await deleteConsolidationLog("prefs");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/consolidation-log`);
    expect(init?.method).toBe("DELETE");
  });

  test("throws a typed ApiError on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_NOT_FOUND", message: "no such file" } }),
    );
    const err = await deleteJournalPeriod("prefs", "ghost").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_NOT_FOUND");
  });
});

describe("getFact", () => {
  test("GETs /memory_stores/<store>/facts/<id> and returns the full fact", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ id: "m-1", title: "tabs", text: "uses tabs", actor: "user" }));
    const out = await getFact("prefs", "m-1");
    expect(out.id).toBe("m-1");
    expect(out.text).toBe("uses tabs");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/facts/m-1`);
    expect(init?.method).toBeUndefined();
  });

  test("URL-encodes the store name and fact id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ id: "x" }));
    await getFact("store with space", "a/b?c");
    expect(fetchMock.mock.calls[0][0]).toContain("store%20with%20space");
    expect(fetchMock.mock.calls[0][0]).toContain("a%2Fb%3Fc");
  });
});

describe("clearFacts", () => {
  test("DELETEs /facts and returns the cleared count", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ cleared: 7 }));
    const n = await clearFacts("prefs");
    expect(n).toBe(7);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/facts`);
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
    expect(url).toBe(`${BASE}/memory_stores/prefs/recall`);
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

describe("getMemoryStoreMetrics", () => {
  test("returns the fact_count + disk_bytes payload as-is", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ fact_count: 5, disk_bytes: 4096 }));
    const out = await getMemoryStoreMetrics("prefs");
    expect(out).toEqual({ fact_count: 5, disk_bytes: 4096 });
  });
});

describe("getMemoryRules", () => {
  test("GETs /memory_stores/<name>/rules and returns the text payload", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ text: "always lint" }));
    const out = await getMemoryRules("prefs");
    expect(out.text).toBe("always lint");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/memory_stores/prefs/rules`);
    expect((fetchMock.mock.calls[0][1] as RequestInit | undefined)?.method).toBeUndefined();
  });

  test("returns null text when the store has no rules", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ text: null }));
    expect((await getMemoryRules("prefs")).text).toBeNull();
  });

  test("throws a typed ApiError on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_NOT_FOUND", message: "no store" } }),
    );
    const err = await getMemoryRules("ghost").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("MEMORY_NOT_FOUND");
  });
});

describe("getMemoryJournal", () => {
  test("GETs /memory_stores/<name>/journal and returns the files list", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        files: [{ period: "2026-06", text: "june", path: "/p/2026-06.md", folder_path: "/p" }],
      }),
    );
    const out = await getMemoryJournal("prefs");
    expect(out.files).toHaveLength(1);
    expect(out.files[0].period).toBe("2026-06");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/memory_stores/prefs/journal`);
  });

  test("URL-encodes the store name", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ files: [] }));
    await getMemoryJournal("store with space");
    expect(fetchMock.mock.calls[0][0]).toContain("store%20with%20space");
  });
});

describe("getMemoryHandoff", () => {
  test("GETs /memory_stores/<name>/handoff and returns the scenes list", async () => {
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
    const out = await getMemoryHandoff("prefs");
    expect(out.scenes[0].branch).toBe("feat/x");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/memory_stores/prefs/handoff`);
  });
});

describe("getMemoryConsolidationLog", () => {
  test("GETs /memory_stores/<name>/consolidation-log and returns the text + path", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ text: "consolidated", path: "/p/log.md", folder_path: "/p" }));
    const out = await getMemoryConsolidationLog("prefs");
    expect(out.text).toBe("consolidated");
    expect(out.path).toBe("/p/log.md");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/memory_stores/prefs/consolidation-log`);
  });

  test("returns null text when absent (still 200)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({ text: null, path: "/p/log.md", folder_path: "/p" }),
    );
    expect((await getMemoryConsolidationLog("prefs")).text).toBeNull();
  });
});
