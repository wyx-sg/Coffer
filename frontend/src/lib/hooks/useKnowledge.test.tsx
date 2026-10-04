// frontend/src/lib/hooks/useKnowledge.test.tsx
//
// The viewer's save, pinned at the wire (spec knowledge "Save a document
// edited in the web UI"): a PUT to `/knowledge/file` carrying the body alone
// and the fingerprint the read returned, the saved file dropped straight into
// its cache entry, and the new fingerprint handed back so a second save does
// not 409 against the first.
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { resetApiClient } from "@/lib/api/client";
import type { PropsWithChildren } from "react";

import { useSaveKnowledgeFile } from "./useKnowledge";
import { ApiError } from "@/lib/api/errors";
import type { FileOut } from "@/lib/api/knowledge";
import { knowledgeFileKey, knowledgeTreeKey } from "@/lib/api/queryKeys";

const SAVED: FileOut = {
  path: "shopee/gateway.md",
  title: "Account Gateway",
  description: "where account decisions are made",
  actor: "user",
  created_at: "2026-09-12T00:00:00Z",
  updated_at: "2026-09-28T00:00:00Z",
  body: "Rewritten.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/gateway.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee",
  fingerprint: "fp-2",
};

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    qc,
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

function stubFetch(payload: unknown, status = 200) {
  // A fresh Response per call: the typed client reads the body, which a
  // single shared one allows only once.
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  // The client binds `fetch` when it is built, so a stub needs a fresh one.
  resetApiClient();
  return fetchMock;
}

describe("useSaveKnowledgeFile", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("PUTs the body with the loaded fingerprint and caches the saved file", async () => {
    const fetchMock = stubFetch(SAVED);
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(knowledgeTreeKey("shopee"), { path: "shopee", directories: [], files: [] });
    const { result } = renderHook(() => useSaveKnowledgeFile(), { wrapper });

    const next = await result.current({
      path: SAVED.path,
      body: "Rewritten.",
      expected_fingerprint: "fp-1",
    });

    expect(next).toBe("fp-2");
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toMatch(/\/knowledge\/file$/);
    expect(request.method).toBe("PUT");
    expect(await request.clone().json()).toEqual({
      path: SAVED.path,
      body: "Rewritten.",
      expected_fingerprint: "fp-1",
    });
    expect(qc.getQueryData(knowledgeFileKey(SAVED.path))).toEqual(SAVED);
    // A title lives in frontmatter and the tree rows show it, so every level
    // is marked for a refetch.
    expect(qc.getQueryState(knowledgeTreeKey("shopee"))?.isInvalidated).toBe(true);
  });

  test("a stale fingerprint rejects with the conflict code and caches nothing", async () => {
    stubFetch({ error: { code: "KNOWLEDGE_FILE_CONFLICT", message: "changed on disk" } }, 409);
    const { qc, wrapper } = makeWrapper();
    const { result } = renderHook(() => useSaveKnowledgeFile(), { wrapper });

    const err = await result
      .current({ path: SAVED.path, body: "x", expected_fingerprint: "fp-old" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("KNOWLEDGE_FILE_CONFLICT");
    expect(qc.getQueryData(knowledgeFileKey(SAVED.path))).toBeUndefined();
  });
});
