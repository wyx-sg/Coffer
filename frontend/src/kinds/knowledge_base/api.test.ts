// frontend/src/kinds/knowledge_base/api.test.ts — TEST22-019
//
// Exercises the KB fetch-based API helpers. The auth helper pulls the
// token from window.__COFFER_TOKEN__ / localStorage; we stub the global
// fetch so each test can verify the URL + method + headers + body
// produced by the helper.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  createKnowledgeBase,
  deleteDocument,
  getKnowledgeBaseMetrics,
  ingestDocument,
  listDocuments,
  searchKnowledgeBase,
} from "./api";

declare global {
  var __COFFER_TOKEN__: string | undefined;
  var __COFFER_BASE_URL__: string | undefined;
}

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

describe("createKnowledgeBase", () => {
  test("POSTs to /knowledge_bases with the token + JSON body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        ref: "knowledge_base:designs",
        kind: "knowledge_base",
        name: "designs",
        description: null,
        config: {
          embedding_model: "m",
          chunk_size: 512,
          chunk_overlap: 64,
          max_document_bytes: 1024,
        },
        enabled: true,
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z",
      }),
    );

    const result = await createKnowledgeBase({
      name: "designs",
      description: null,
      config: {
        embedding_model: "m",
        chunk_size: 512,
        chunk_overlap: 64,
        max_document_bytes: 1024,
      },
    });
    expect(result.name).toBe("designs");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge_bases`);
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
    expect(headers["X-Coffer-Actor"]).toBe("ui");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(typeof init?.body).toBe("string");
    expect(JSON.parse(init!.body as string)).toMatchObject({ name: "designs" });
  });

  test("throws on a non-2xx response with the error envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(409, { error: { code: "RESOURCE_ALREADY_EXISTS" } }),
    );
    await expect(
      createKnowledgeBase({
        name: "dup",
        description: null,
        config: {
          embedding_model: "m",
          chunk_size: 512,
          chunk_overlap: 64,
          max_document_bytes: 1024,
        },
      }),
    ).rejects.toThrow(/HTTP 409/);
  });
});

describe("listDocuments", () => {
  test("GETs /knowledge_bases/<name>/documents with paging params", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ documents: [], total: 0 }));

    const out = await listDocuments("kb1", 25, 50);
    expect(out).toEqual({ documents: [], total: 0 });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge_bases/kb1/documents?limit=25&offset=50`);
  });

  test("URL-encodes the kb name to defend against weird characters", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ documents: [], total: 0 }));
    await listDocuments("kb with space");
    expect(fetchMock.mock.calls[0][0]).toContain("kb%20with%20space");
  });
});

describe("ingestDocument", () => {
  test("POSTs multipart/form-data with the file + replace flag", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        id: "abc123",
        kb_name: "kb1",
        filename: "a.md",
        extension: ".md",
        size_bytes: 5,
        sha256: "deadbeef",
        chunk_count: 1,
        ingested_at: "2026-05-29T00:00:00Z",
      }),
    );

    const file = new File([new Blob(["alpha"])], "a.md", { type: "text/markdown" });
    const out = await ingestDocument("kb1", file, true);
    expect(out.id).toBe("abc123");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge_bases/kb1/documents`);
    expect(init?.method).toBe("POST");
    // Body is a FormData; verify replace is the string "true" so the server
    // FastAPI form coercer reads it as a bool.
    const body = init?.body as FormData;
    expect(body.get("replace")).toBe("true");
    expect((body.get("file") as File).name).toBe("a.md");
  });
});

describe("deleteDocument", () => {
  test("DELETEs the document URL with the token", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({})); // 200 with empty payload — checkOk only cares about ok

    await deleteDocument("kb1", "doc-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge_bases/kb1/documents/doc-1`);
    expect(init?.method).toBe("DELETE");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
  });

  test("throws on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "DOCUMENT_NOT_FOUND" } }),
    );
    await expect(deleteDocument("kb1", "nope")).rejects.toThrow(/HTTP 404/);
  });
});

describe("searchKnowledgeBase", () => {
  test("POSTs query + top_k to /search and unwraps the hits array", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        hits: [
          {
            text: "alpha bravo",
            document_id: "d1",
            filename: "a.md",
            score: 0.7,
            position: 0,
          },
        ],
      }),
    );

    const hits = await searchKnowledgeBase("kb1", "alpha", 3);
    expect(hits).toHaveLength(1);
    expect(hits[0].text).toContain("alpha");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge_bases/kb1/search`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init!.body as string)).toEqual({ query: "alpha", top_k: 3 });
  });

  test("defaults top_k to 5 when omitted", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ hits: [] }));

    await searchKnowledgeBase("kb1", "anything");
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({
      query: "anything",
      top_k: 5,
    });
  });
});

describe("getKnowledgeBaseMetrics", () => {
  test("returns the document_count + disk_bytes payload as-is", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({ document_count: 3, disk_bytes: 1234 }),
    );
    const out = await getKnowledgeBaseMetrics("kb1");
    expect(out).toEqual({ document_count: 3, disk_bytes: 1234 });
  });
});
