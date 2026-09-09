// frontend/src/pages/KnowledgePage.test.tsx — TEST26-014
//
// KnowledgePage mirrors SkillsPage: PageHeader + welcome panel (empty) /
// DataTable (populated). It loads from the DEDICATED `/knowledge` endpoint (not
// the generic `/resources` list) because only that endpoint carries the typed
// `scope` discriminator the table's scope column needs, plus BOTH per-lane
// counts (entries and documents stay separate numbers).

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { KnowledgePage } from "./KnowledgePage";
import type { ScopeListOut, ScopeOut } from "@/kinds/knowledge/api";

// Partial mock: stub only the network call; keep the real `deriveScope` the
// table uses to classify the scope column.
vi.mock("@/kinds/knowledge/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/knowledge/api")>()),
  listScopes: vi.fn(),
}));
const api = await import("@/kinds/knowledge/api");
const listScopesMock = vi.mocked(api.listScopes);

afterEach(() => vi.clearAllMocks());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

// Mirrors the real `/knowledge` payload: top-level `scope` + `project_id`,
// NOT inside `config` (the bug: the generic /resources row omits both).
const GLOBAL_SCOPE: ScopeOut = {
  ref: "knowledge:global",
  kind: "knowledge",
  name: "global",
  scope: "global",
  project_id: "00000000000000000000000000",
  project_root: null,
  description: "Global agent knowledge",
  config: {
    retrieval_modes: ["grep", "keyword"],
    default_mode: "keyword",
    max_entry_chars: 8192,
    chunk_size: 512,
    chunk_overlap: 64,
    max_document_bytes: 26214400,
    auto_update_sources: false,
  },
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

function resolveWith(scopes: ScopeOut[]) {
  listScopesMock.mockResolvedValue({ scopes } as ScopeListOut);
}

describe("KnowledgePage", () => {
  test("renders the loading state while scopes are pending", () => {
    listScopesMock.mockReturnValue(new Promise(() => {}) as Promise<ScopeListOut>);
    render(<KnowledgePage />, { wrapper: wrap() });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the empty state, whose only CTA creates a NAMED collection", async () => {
    resolveWith([]);
    render(<KnowledgePage />, { wrapper: wrap() });
    expect(
      await screen.findByText(/one place for everything your agents know/i),
    ).toBeInTheDocument();
    // The global / per-project scopes auto-provision; the only thing a person
    // creates by hand is a collection.
    expect(screen.getByRole("button", { name: /new collection/i })).toBeInTheDocument();
  });

  test("renders the populated list when scopes exist", async () => {
    resolveWith([GLOBAL_SCOPE]);
    render(<KnowledgePage />, { wrapper: wrap() });
    expect(await screen.findByText("global")).toBeInTheDocument();
  });

  test("labels the global scope as Global, not Unknown", async () => {
    // The real /knowledge payload carries a top-level `scope`; the table
    // must surface it instead of the indeterminate "Unknown" fallback (which
    // is what the scope-less generic /resources row produced — the bug).
    resolveWith([GLOBAL_SCOPE]);
    render(<KnowledgePage />, { wrapper: wrap() });
    expect(await screen.findByText("Global")).toBeInTheDocument();
    expect(screen.queryByText("Unknown")).not.toBeInTheDocument();
  });

  test("renders an error card when the scopes query fails", async () => {
    listScopesMock.mockRejectedValue(new Error("HTTP 500"));
    render(<KnowledgePage />, { wrapper: wrap() });
    expect(await screen.findByText("Failed to load knowledge scopes")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
  });

  test("the header Add action opens the new-collection dialog", async () => {
    resolveWith([GLOBAL_SCOPE]);
    render(<KnowledgePage />, { wrapper: wrap() });
    fireEvent.click(await screen.findByRole("button", { name: /new collection/i }));
    expect(screen.getByLabelText(/^name$/i)).toBeInTheDocument();
    // The auto-provisioned scopes are never offered as a name to type.
    expect(screen.getByText(/reserved for the automatic scopes/i)).toBeInTheDocument();
  });

  test("shows entries and documents as two columns, never one summed count", async () => {
    resolveWith([{ ...GLOBAL_SCOPE, entry_count: 3, document_count: 5 }]);
    render(<KnowledgePage />, { wrapper: wrap() });
    expect(await screen.findByRole("columnheader", { name: "Entries" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.queryByText("8")).not.toBeInTheDocument();
  });
});
