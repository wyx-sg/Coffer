// frontend/src/lib/hooks/useKnowledge.test.ts
// The unified 知识 query bindings: scopes from memory stores, an intermixed
// notes+documents list for a scope, the trash, and mutations. Mocks the two
// underlying api modules (the network boundary) and renders the hooks through a
// real QueryClientProvider.
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type PropsWithChildren } from "react";

vi.mock("@/kinds/memory/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/memory/api")>()),
  listMemoryStores: vi.fn(),
  listFacts: vi.fn(),
}));
vi.mock("@/kinds/knowledge_base/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/knowledge_base/api")>()),
  listKnowledgeBases: vi.fn(),
  listDocuments: vi.fn(),
}));

const memApi = await import("@/kinds/memory/api");
const kbApi = await import("@/kinds/knowledge_base/api");
const { useKnowledgeScopes, useKnowledgeItems, useKnowledgeTrash } = await import("./useKnowledge");
const { WORKSPACE_GLOBAL_PROJECT_ID } = await import("@/lib/api/knowledge");
import type { KnowledgeScope } from "@/lib/api/knowledge";

afterEach(() => vi.clearAllMocks());

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

const GLOBAL_SCOPE: KnowledgeScope = {
  id: WORKSPACE_GLOBAL_PROJECT_ID,
  kind: "global",
  label: "",
  projectRoot: null,
  memoryStoreName: "global",
};

describe("useKnowledgeScopes", () => {
  test("derives the scope axis from the memory stores", async () => {
    vi.mocked(memApi.listMemoryStores).mockResolvedValue({
      memory_stores: [
        {
          ref: "m:g",
          kind: "memory",
          name: "global",
          scope: "global",
          project_id: WORKSPACE_GLOBAL_PROJECT_ID,
          project_root: null,
          description: null,
          config: {
            retrieval_modes: ["keyword"],
            default_mode: "keyword",
            embedding_dimensions: 768,
            max_fact_chars: 8192,
          },
          enabled: true,
          created_at: "t",
          updated_at: "t",
        },
      ],
    });
    const { result } = renderHook(() => useKnowledgeScopes(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data?.[0].memoryStoreName).toBe("global");
  });
});

describe("useKnowledgeItems", () => {
  test("merges the scope's notes and the per-KB documents, newest first", async () => {
    vi.mocked(memApi.listFacts).mockResolvedValue({
      facts: [
        {
          id: "f1",
          store_name: "global",
          scope: "global",
          name: "note one",
          description: "",
          text: "body",
          actor: "agent",
          created_at: "t",
          updated_at: "2026-06-10T00:00:00Z",
        },
      ],
      total: 1,
    });
    vi.mocked(kbApi.listDocuments).mockResolvedValue({
      documents: [
        {
          id: "d1",
          kind: "knowledge_base",
          resource_name: "kb1",
          title: "doc one",
          source_mode: "converted",
          content_sha256: "x",
          locked: false,
          project_id: WORKSPACE_GLOBAL_PROJECT_ID,
          deleted_at: null,
          metadata: {},
          created_at: "t",
          updated_at: "2026-06-20T00:00:00Z",
        },
      ],
      total: 1,
    });

    const kbs = [{ name: "kb1" }] as Parameters<typeof useKnowledgeItems>[1];
    const { result } = renderHook(() => useKnowledgeItems(GLOBAL_SCOPE, kbs), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const items = result.current.data ?? [];
    expect(items.map((i) => i.type)).toEqual(["document", "note"]); // newest (doc) first
    // The KB document was listed under the scope's project_id.
    expect(kbApi.listDocuments).toHaveBeenCalledWith("kb1", {
      limit: 200,
      projectId: WORKSPACE_GLOBAL_PROJECT_ID,
    });
  });

  test("does not list facts when the scope has no memory store", async () => {
    vi.mocked(kbApi.listDocuments).mockResolvedValue({ documents: [], total: 0 });
    const noStore = { ...GLOBAL_SCOPE, memoryStoreName: null };
    const kbs = [{ name: "kb1" }] as Parameters<typeof useKnowledgeItems>[1];
    const { result } = renderHook(() => useKnowledgeItems(noStore, kbs), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(memApi.listFacts).not.toHaveBeenCalled();
  });
});

describe("useKnowledgeTrash", () => {
  test("lists soft-deleted documents across KBs with deleted=true", async () => {
    vi.mocked(kbApi.listDocuments).mockResolvedValue({
      documents: [
        {
          id: "d9",
          kind: "knowledge_base",
          resource_name: "kb1",
          title: "trashed",
          source_mode: "converted",
          content_sha256: "x",
          locked: false,
          project_id: WORKSPACE_GLOBAL_PROJECT_ID,
          deleted_at: "2026-06-19T00:00:00Z",
          metadata: {},
          created_at: "t",
          updated_at: "t",
        },
      ],
      total: 1,
    });
    const kbs = [{ name: "kb1" }] as Parameters<typeof useKnowledgeTrash>[1];
    const { result } = renderHook(() => useKnowledgeTrash(GLOBAL_SCOPE, kbs), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.data?.length).toBe(1));
    expect(kbApi.listDocuments).toHaveBeenCalledWith("kb1", {
      limit: 200,
      projectId: WORKSPACE_GLOBAL_PROJECT_ID,
      deleted: true,
    });
    expect(result.current.data?.[0].deletedAt).toBe("2026-06-19T00:00:00Z");
  });
});
