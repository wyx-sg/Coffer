// frontend/src/components/knowledge/KnowledgeTable.test.tsx
//
// The memory-stores list (the /memory landing surface). Asserts the
// human-readable project identity (spec knowledge FR-017a): a per-project store is
// shown by its root directory's basename + absolute path rather than the opaque
// project-<ULID> store name, with the global store and untracked projects
// falling back to the raw name.

import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import { KnowledgeTable } from "@/components/knowledge/KnowledgeTable";
import type { ScopeOut } from "@/kinds/knowledge/api";

vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useDeleteResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function makeStore(overrides: Partial<ScopeOut> = {}): ScopeOut {
  return {
    ref: "knowledge:global",
    kind: "knowledge",
    name: "global",
    scope: "global",
    project_id: "0".repeat(26),
    project_root: null,
    description: null,
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
    entry_count: 0,
    created_at: "2026-05-29T00:00:00Z",
    updated_at: "2026-05-29T00:00:00Z",
    ...overrides,
  };
}

describe("KnowledgeTable — readable project identity (FR-017a)", () => {
  test("has no Scope column — the Name cell already tells the kinds apart", () => {
    render(wrap(<KnowledgeTable items={[makeStore()]} />));
    expect(screen.queryByRole("columnheader", { name: "Scope" })).not.toBeInTheDocument();
    expect(screen.queryByText("Global")).not.toBeInTheDocument();
  });

  test("counts notes and documents in their own columns", () => {
    render(wrap(<KnowledgeTable items={[makeStore({ entry_count: 3, document_count: 5 })]} />));
    expect(screen.getByRole("columnheader", { name: "Notes" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  test("a per-project store shows its directory basename + absolute path, not the ULID", () => {
    const store = makeStore({
      name: "project-01HXYZ00000000000000000000",
      scope: "project",
      project_id: "01HXYZ00000000000000000000",
      project_root: "/Users/me/code/coffer",
    });
    render(wrap(<KnowledgeTable items={[store]} />));

    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("/Users/me/code/coffer")).toBeInTheDocument();
    // The opaque store name is never shown to the user as the label.
    expect(screen.queryByText("project-01HXYZ00000000000000000000")).not.toBeInTheDocument();
  });

  test("the global store reads as 'global'", () => {
    render(wrap(<KnowledgeTable items={[makeStore()]} />));
    expect(screen.getByText("global")).toBeInTheDocument();
  });

  test("a project store with an unknown root falls back to the store name", () => {
    const store = makeStore({
      name: "project-01HUNTRACKED00000000000000",
      scope: "project",
      project_id: "01HUNTRACKED00000000000000",
      project_root: null,
    });
    render(wrap(<KnowledgeTable items={[store]} />));
    expect(screen.getByText("project-01HUNTRACKED00000000000000")).toBeInTheDocument();
  });
});
