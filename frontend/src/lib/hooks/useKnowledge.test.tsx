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
  curated_at: "2026-09-13T00:00:00Z",
  body: "Rewritten.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/gateway.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee",
  fingerprint: "fp-2",
  inbox: false,
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

function stubFetch(payload: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({ ok, status, json: async () => payload });
  vi.stubGlobal("fetch", fetchMock);
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
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/knowledge\/file$/);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
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
    stubFetch(
      { error: { code: "KNOWLEDGE_FILE_CONFLICT", message: "changed on disk" } },
      false,
      409,
    );
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
