// frontend/src/lib/hooks/useKnowledge.test.tsx
//
// The knowledge hooks that write, pinned at the wire: rewriting a collection's
// description (PUT `/knowledge/collections/{uid}/description`) and deleting a
// document (DELETE `/knowledge/file`), which drops the file's own cache entry
// and marks the rest of the knowledge subtree for a refetch. There is no save
// hook: a person changes a document in their own editor.
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { resetApiClient } from "@/lib/api/client";
import type { PropsWithChildren } from "react";

import { useDeleteKnowledgeFile, useDescribeCollection } from "./useKnowledge";
import { knowledgeCollectionsKey, knowledgeFileKey, knowledgeTreeKey } from "@/lib/api/queryKeys";

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
  const fetchMock = vi.fn().mockImplementation(async () =>
    status === 204
      ? new Response(null, { status })
      : new Response(JSON.stringify(payload), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
  );
  vi.stubGlobal("fetch", fetchMock);
  // The client binds `fetch` when it is built, so a stub needs a fresh one.
  resetApiClient();
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("useDescribeCollection", () => {
  test("PUTs the description for the collection's uid and refreshes the subtree", async () => {
    const fetchMock = stubFetch({
      uid: "kn-1",
      name: "shopee",
      description: "Shops and owners.",
      document_count: 0,
      folder_path: "/x",
      updated_at: null,
      tidy_handoff: { prompt: "p" },
    });
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(knowledgeCollectionsKey, { collections: [] });
    const { result } = renderHook(() => useDescribeCollection("kn-1"), { wrapper });

    await act(() => result.current.mutateAsync("Shops and owners."));

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toMatch(/\/knowledge\/collections\/kn-1\/description$/);
    expect(request.method).toBe("PUT");
    expect(await request.clone().json()).toEqual({ description: "Shops and owners." });
    expect(qc.getQueryState(knowledgeCollectionsKey)?.isInvalidated).toBe(true);
  });
});

describe("useDeleteKnowledgeFile", () => {
  test("DELETEs the path, drops its cache entry and refreshes the tree", async () => {
    const fetchMock = stubFetch(null, 204);
    const { qc, wrapper } = makeWrapper();
    qc.setQueryData(knowledgeFileKey("shopee/gateway.md"), { path: "shopee/gateway.md" });
    qc.setQueryData(knowledgeTreeKey("shopee"), { path: "shopee", directories: [], files: [] });
    const { result } = renderHook(() => useDeleteKnowledgeFile(), { wrapper });

    await act(() => result.current.mutateAsync("shopee/gateway.md"));

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("DELETE");
    expect(new URL(request.url).searchParams.get("path")).toBe("shopee/gateway.md");
    expect(qc.getQueryData(knowledgeFileKey("shopee/gateway.md"))).toBeUndefined();
    expect(qc.getQueryState(knowledgeTreeKey("shopee"))?.isInvalidated).toBe(true);
  });
});
