// frontend/src/kinds/memory/api.test.ts — TEST26-014
//
// Exercises the memory fetch-based API helpers. The auth helper pulls the
// token from window.__COFFER_TOKEN__; we stub the global fetch so each
// test can verify URL + method + headers + body.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  addMemory,
  clearMemories,
  createMemoryStore,
  deleteMemory,
  getMemoryStoreMetrics,
  listMemories,
  searchMemories,
  updateMemory,
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

describe("createMemoryStore", () => {
  test("POSTs to /memory_stores with the token + JSON body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        ref: "memory:prefs",
        kind: "memory",
        name: "prefs",
        description: null,
        config: {
          embedding_model: "BAAI/bge-small-en-v1.5",
          llm_provider: "none",
          llm_model: null,
          llm_endpoint: null,
          llm_credential_ref: null,
          max_memory_chars: 8192,
        },
        enabled: true,
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z",
      }),
    );

    const result = await createMemoryStore({
      name: "prefs",
      description: null,
      config: {
        embedding_model: "BAAI/bge-small-en-v1.5",
        llm_provider: "none",
        llm_model: null,
        llm_endpoint: null,
        llm_credential_ref: null,
        max_memory_chars: 8192,
      },
    });
    expect(result.name).toBe("prefs");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores`);
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
    expect(headers["X-Coffer-Actor"]).toBe("user");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init!.body as string)).toMatchObject({ name: "prefs" });
  });

  test("throws on a non-2xx response with the error envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(409, { error: { code: "RESOURCE_ALREADY_EXISTS" } }),
    );
    await expect(
      createMemoryStore({
        name: "dup",
        description: null,
        config: {
          embedding_model: "m",
          llm_provider: "none",
          llm_model: null,
          llm_endpoint: null,
          llm_credential_ref: null,
          max_memory_chars: 8192,
        },
      }),
    ).rejects.toThrow(/HTTP 409/);
  });
});

describe("listMemories", () => {
  test("GETs /memory_stores/<name>/memories with paging params", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ memories: [], total: 0 }));

    const out = await listMemories("prefs", 25, 50);
    expect(out).toEqual({ memories: [], total: 0 });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/memories?limit=25&offset=50`);
  });

  test("URL-encodes the store name", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ memories: [], total: 0 }));
    await listMemories("store with space");
    expect(fetchMock.mock.calls[0][0]).toContain("store%20with%20space");
  });

  test("defaults limit/offset to 50/0", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ memories: [], total: 0 }));
    await listMemories("prefs");
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${BASE}/memory_stores/prefs/memories?limit=50&offset=0`,
    );
  });
});

describe("addMemory", () => {
  test("POSTs the text to /memory_stores/<store>/memories", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        id: "m-1",
        store_name: "prefs",
        text: "uses tabs",
        actor: "user",
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z",
      }),
    );

    const out = await addMemory("prefs", "uses tabs");
    expect(out.id).toBe("m-1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/memories`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init!.body as string)).toEqual({ text: "uses tabs" });
  });

  test("throws on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(503, { error: { code: "LLM_NOT_CONFIGURED" } }),
    );
    await expect(addMemory("prefs", "hi")).rejects.toThrow(/HTTP 503/);
  });
});

describe("updateMemory", () => {
  test("PATCHes the new text to the memory id URL", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        id: "m-1",
        store_name: "prefs",
        text: "new text",
        actor: "user",
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z",
      }),
    );

    await updateMemory("prefs", "m-1", "new text");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/memories/m-1`);
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init!.body as string)).toEqual({ text: "new text" });
  });
});

describe("deleteMemory", () => {
  test("DELETEs /memory_stores/<store>/memories/<id> with the token", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));

    await deleteMemory("prefs", "m-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/memories/m-1`);
    expect(init?.method).toBe("DELETE");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
  });

  test("throws on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "MEMORY_NOT_FOUND" } }),
    );
    await expect(deleteMemory("prefs", "ghost")).rejects.toThrow(/HTTP 404/);
  });
});

describe("clearMemories", () => {
  test("POSTs /memory_stores/<store>/memories/clear and returns the count", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ cleared: 7 }));

    const n = await clearMemories("prefs");
    expect(n).toBe(7);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/memories/clear`);
    expect(init?.method).toBe("POST");
  });
});

describe("searchMemories", () => {
  test("POSTs query + top_k to /search and unwraps hits", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        hits: [
          {
            id: "m-1",
            text: "uses tabs",
            score: 0.92,
            created_at: "2026-05-29T00:00:00Z",
          },
        ],
      }),
    );

    const hits = await searchMemories("prefs", "tabs", 3);
    expect(hits).toHaveLength(1);
    expect(hits[0].text).toBe("uses tabs");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/memory_stores/prefs/search`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init!.body as string)).toEqual({ query: "tabs", top_k: 3 });
  });

  test("defaults top_k to 5 when omitted", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ hits: [] }));
    await searchMemories("prefs", "anything");
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({
      query: "anything",
      top_k: 5,
    });
  });
});

describe("getMemoryStoreMetrics", () => {
  test("returns the memory_count + disk_bytes payload as-is", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ memory_count: 5, disk_bytes: 4096 }));
    const out = await getMemoryStoreMetrics("prefs");
    expect(out).toEqual({ memory_count: 5, disk_bytes: 4096 });
  });
});
