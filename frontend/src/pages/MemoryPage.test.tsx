// frontend/src/pages/MemoryPage.test.tsx — TEST26-014
//
// MemoryPage mirrors SkillsPage: PageHeader + welcome panel (empty) / DataTable
// (populated). It loads from the DEDICATED `/memory_stores` endpoint (not the
// generic `/resources` list) because only that endpoint carries the typed
// `scope`/`project_id` the table's scope column needs — the generic resource
// row has neither, so it would mislabel every store as "Unknown".

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { MemoryPage } from "./MemoryPage";
import type { MemoryStoreListOut, MemoryStoreOut } from "@/kinds/memory/api";

// Partial mock: stub only the network call; keep the real `deriveScope` the
// table uses to classify the scope column.
vi.mock("@/kinds/memory/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/memory/api")>()),
  listMemoryStores: vi.fn(),
}));
const api = await import("@/kinds/memory/api");
const listMemoryStoresMock = vi.mocked(api.listMemoryStores);

afterEach(() => vi.clearAllMocks());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

// Mirrors the real `/memory_stores` payload: top-level `scope` + `project_id`,
// NOT inside `config` (the bug: the generic /resources row omits both).
const GLOBAL_STORE: MemoryStoreOut = {
  ref: "memory:global",
  kind: "memory",
  name: "global",
  scope: "global",
  project_id: "00000000000000000000000000",
  project_root: null,
  description: "Global agent memory",
  config: {
    retrieval_modes: ["grep", "keyword"],
    default_mode: "keyword",
    embedding_provider: null,
    embedding_model: null,
    embedding_base_url: null,
    embedding_credential_ref: null,
    embedding_dimensions: 768,
    max_fact_chars: 8192,
  },
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

function resolveWith(stores: MemoryStoreOut[]) {
  listMemoryStoresMock.mockResolvedValue({ memory_stores: stores } as MemoryStoreListOut);
}

describe("MemoryPage", () => {
  test("renders the loading state while stores are pending", () => {
    listMemoryStoresMock.mockReturnValue(new Promise(() => {}) as Promise<MemoryStoreListOut>);
    render(<MemoryPage />, { wrapper: wrap() });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the empty state (no Add CTA — stores are auto-provisioned)", async () => {
    resolveWith([]);
    render(<MemoryPage />, { wrapper: wrap() });
    expect(await screen.findByText(/your shared agent memory/i)).toBeInTheDocument();
    expect(screen.queryByText(/new memory store/i)).not.toBeInTheDocument();
  });

  test("renders the populated list when memory stores exist", async () => {
    resolveWith([GLOBAL_STORE]);
    render(<MemoryPage />, { wrapper: wrap() });
    expect(await screen.findByText("global")).toBeInTheDocument();
  });

  test("labels the global store's scope as Global, not Unknown", async () => {
    // The real /memory_stores payload carries a top-level `scope`; the table
    // must surface it instead of the indeterminate "Unknown" fallback (which
    // is what the scope-less generic /resources row produced — the bug).
    resolveWith([GLOBAL_STORE]);
    render(<MemoryPage />, { wrapper: wrap() });
    expect(await screen.findByText("Global")).toBeInTheDocument();
    expect(screen.queryByText("Unknown")).not.toBeInTheDocument();
  });

  test("renders an error card when the stores query fails", async () => {
    listMemoryStoresMock.mockRejectedValue(new Error("HTTP 500"));
    render(<MemoryPage />, { wrapper: wrap() });
    expect(await screen.findByText("Failed to load memory stores")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
  });
});
