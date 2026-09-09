// frontend/src/kinds/knowledge/document-api.test.ts
//
// Exercises the DOCUMENT-lane fetch helpers of the one `knowledge` kind (plus
// the scope create / read / config-patch calls the documents surface drives).
// The auth helper reads the token from the dev-injected window globals, else
// localStorage; these tests seed the globals and stub the global fetch so each
// test can verify the URL + method + headers + body produced by the helper.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import {
  createScope,
  deleteDocument,
  getDocument,
  getScope,
  getScopeMetrics,
  getDocumentStatus,
  ingestDocument,
  listDocuments,
  reconvertDocument,
  reembedDocuments,
  reindexScope,
  searchDocuments,
  updateScopeConfig,
  type RetrievalMode,
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

describe("createScope", () => {
  test("POSTs to /knowledge with the token + JSON body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        ref: "knowledge:designs",
        kind: "knowledge",
        name: "designs",
        description: null,
        config: { retrieval_modes: ["keyword", "grep"], default_mode: "keyword" },
        enabled: true,
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z",
      }),
    );

    const result = await createScope({
      name: "designs",
      description: null,
      config: { retrieval_modes: ["keyword", "grep"], default_mode: "keyword" },
    });
    expect(result.name).toBe("designs");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge`);
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
    expect(headers["X-Coffer-Actor"]).toBe("user");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init!.body as string)).toMatchObject({ name: "designs" });
  });

  test("throws a typed ApiError carrying the envelope code + message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(409, {
        error: { code: "RESOURCE_ALREADY_EXISTS", message: "already exists" },
      }),
    );
    const err = await createScope({
      name: "dup",
      description: null,
      config: {},
    }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("RESOURCE_ALREADY_EXISTS");
    expect((err as ApiError).message).toBe("already exists");
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
    const err = await createScope({ name: "x", description: null, config: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("INTERNAL_ERROR");
  });
});

describe("listDocuments", () => {
  test("GETs /knowledge/<scope>/documents with paging params", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ documents: [], total: 0 }));

    const out = await listDocuments("designs", 25, 50);
    expect(out).toEqual({ documents: [], total: 0 });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/documents?limit=25&offset=50`);
  });

  test("URL-encodes the kb name to defend against weird characters", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ documents: [], total: 0 }));
    await listDocuments("kb with space");
    expect(fetchMock.mock.calls[0][0]).toContain("kb%20with%20space");
  });

  test("appends an encoded &q=<filter> when a title filter is given", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ documents: [], total: 0 }));
    await listDocuments("designs", 50, 0, "run book");
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${BASE}/knowledge/designs/documents?limit=50&offset=0&q=run%20book`,
    );
  });

  test("omits q when the filter is empty/blank", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ documents: [], total: 0 }));
    await listDocuments("designs", 50, 0, "   ");
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${BASE}/knowledge/designs/documents?limit=50&offset=0`,
    );
  });
});

describe("getDocument", () => {
  test("GETs the document detail (markdown + frontmatter)", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        okJson({ id: "d1", title: "a", source_mode: "converted", markdown: "# hi" }),
      );
    const out = await getDocument("designs", "d1");
    expect(out.markdown).toBe("# hi");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/knowledge/designs/documents/d1`);
  });
});

describe("ingestDocument", () => {
  test("POSTs multipart/form-data with the file + replace flag", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ id: "abc123", title: "a.md", source_mode: "converted" }));

    const file = new File([new Blob(["alpha"])], "a.md", { type: "text/markdown" });
    const out = await ingestDocument("designs", file, true);
    expect(out.id).toBe("abc123");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/documents`);
    expect(init?.method).toBe("POST");
    const body = init?.body as FormData;
    expect(body.get("replace")).toBe("true");
    expect((body.get("file") as File).name).toBe("a.md");
  });
});

describe("deleteDocument", () => {
  test("DELETEs the document URL with the token", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({}));

    await deleteDocument("designs", "doc-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/documents/doc-1`);
    expect(init?.method).toBe("DELETE");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
  });

  test("throws a typed ApiError with the envelope code on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(404, { error: { code: "DOCUMENT_NOT_FOUND", message: "no such doc" } }),
    );
    const err = await deleteDocument("designs", "nope").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("DOCUMENT_NOT_FOUND");
  });
});

describe("reindexScope", () => {
  test("POSTs to /reindex and returns the scan result", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        okJson({ documents_scanned: 3, documents_reindexed: 1, documents_skipped: 2 }),
      );
    const out = await reindexScope("designs");
    expect(out.documents_reindexed).toBe(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/reindex`);
    expect(init?.method).toBe("POST");
  });
});

describe("searchDocuments", () => {
  test("POSTs query + top_k (no mode) and returns the SearchResponse", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        passages: [
          { text: "alpha bravo", document_id: "d1", title: "a.md", score: 0.7, position: 0 },
        ],
      }),
    );

    const out = await searchDocuments("designs", "alpha", { topK: 3 });
    expect(out.passages).toHaveLength(1);
    expect(out.passages[0].text).toContain("alpha");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/search`);
    expect(init?.method).toBe("POST");
    // "One query → one answer": the request carries no mode.
    expect(JSON.parse(init!.body as string)).toEqual({ query: "alpha", top_k: 3 });
  });

  test("defaults top_k to 5 and never sends mode", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJson({ passages: [] }));

    await searchDocuments("designs", "anything");
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({
      query: "anything",
      top_k: 5,
    });
  });
});

describe("getScope", () => {
  test("GETs the scope endpoint, which always returns a complete normalized config", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        ref: "knowledge:designs",
        kind: "knowledge",
        name: "designs",
        description: null,
        config: { retrieval_modes: ["keyword", "grep"], default_mode: "keyword" },
        enabled: true,
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z",
      }),
    );
    const out = await getScope("designs");
    expect(out.config.retrieval_modes).toEqual(["keyword", "grep"]);
    const [url, init] = fetchMock.mock.calls[0];
    // The scope endpoint re-parses the stored config through KnowledgeConfig
    // and always returns a complete config; the raw /resources endpoint can omit
    // fields like retrieval_modes and crash the settings dialog. Reads must use
    // this endpoint.
    expect(url).toBe(`${BASE}/knowledge/designs`);
    expect(init?.method).toBeUndefined();
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
  });
});

describe("updateScopeConfig", () => {
  test("PATCHes /knowledge/<scope> with just the changed fields (the backend merges)", async () => {
    const config = {
      retrieval_modes: ["keyword", "grep", "vector"] as RetrievalMode[],
      default_mode: "keyword" as RetrievalMode,
      chunk_size: 800,
      chunk_overlap: 80,
      max_document_bytes: 1048576,
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        ref: "knowledge:designs",
        kind: "knowledge",
        name: "designs",
        description: null,
        config,
        enabled: true,
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z",
      }),
    );

    const out = await updateScopeConfig("designs", config);
    expect(out.config.chunk_size).toBe(800);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs`);
    expect(init?.method).toBe("PATCH");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init!.body as string)).toEqual(config);
  });

  test("throws a typed ApiError with the envelope code on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(422, {
        error: { code: "CONFIG_VALIDATION_ERROR", message: "chunk_size out of range" },
      }),
    );
    const err = await updateScopeConfig("designs", { chunk_size: 1 }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("CONFIG_VALIDATION_ERROR");
  });
});

describe("reconvertDocument", () => {
  test("POSTs to the per-document reconvert URL", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ id: "d1", title: "a.md", source_mode: "converted" }));

    const out = await reconvertDocument("designs", "d1");
    expect(out.source_mode).toBe("converted");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/documents/d1/reconvert`);
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
  });

  test("surfaces RECONVERSION_BLOCKED (409, source_mode=edited) as a typed ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(409, {
        error: { code: "RECONVERSION_BLOCKED", message: "document was edited" },
      }),
    );
    const err = await reconvertDocument("designs", "d1").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("RECONVERSION_BLOCKED");
  });
});

describe("getScopeMetrics", () => {
  test("returns the metrics payload as-is", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okJson({
        document_count: 3,
        chunk_count: 12,
        documents_degraded: 0,
        indexed_modes: ["keyword"],
        disk_bytes: 1234,
      }),
    );
    const out = await getScopeMetrics("designs");
    expect(out).toEqual({
      document_count: 3,
      chunk_count: 12,
      documents_degraded: 0,
      indexed_modes: ["keyword"],
      disk_bytes: 1234,
    });
  });
});

describe("reembedDocuments", () => {
  test("POSTs the reembed-batch body and returns the counts", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ queued: 2, skipped: 1, total: 3 }));
    const out = await reembedDocuments("designs", { all: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/documents/reembed-batch`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ all: true });
    expect(out).toEqual({ queued: 2, skipped: 1, total: 3 });
  });

  test("surfaces the error envelope as a typed ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      notOkJson(500, { error: { code: "INTERNAL_ERROR", message: "boom" } }),
    );
    const err = await reembedDocuments("designs", { document_ids: ["d1"] }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("INTERNAL_ERROR");
  });
});

describe("getDocumentStatus", () => {
  test("GETs the status endpoint and returns the in-flight statuses", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okJson({ statuses: [{ document_id: "d1", state: "running" }] }));
    const out = await getDocumentStatus("designs");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/knowledge/designs/documents/status`);
    expect(init?.method ?? "GET").toBe("GET");
    expect(out.statuses[0]).toEqual({ document_id: "d1", state: "running" });
  });
});
