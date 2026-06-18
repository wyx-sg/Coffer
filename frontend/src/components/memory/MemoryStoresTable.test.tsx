// frontend/src/components/memory/MemoryStoresTable.test.tsx
//
// The memory-stores list (the /memory landing surface). Asserts the
// human-readable project identity (spec 007 FR-017a): a per-project store is
// shown by its root directory's basename + absolute path rather than the opaque
// project-<ULID> store name, with the global store and untracked projects
// falling back to the raw name.

import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import { MemoryStoresTable } from "./MemoryStoresTable";
import type { MemoryStoreOut } from "@/kinds/memory/api";

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

function makeStore(overrides: Partial<MemoryStoreOut> = {}): MemoryStoreOut {
  return {
    ref: "memory:global",
    kind: "memory",
    name: "global",
    scope: "global",
    project_id: "0".repeat(26),
    project_root: null,
    description: null,
    config: {
      retrieval_modes: ["grep", "keyword"],
      default_mode: "keyword",
      embedding_dimensions: 768,
      max_fact_chars: 8192,
    },
    enabled: true,
    fact_count: 0,
    created_at: "2026-05-29T00:00:00Z",
    updated_at: "2026-05-29T00:00:00Z",
    ...overrides,
  };
}

describe("MemoryStoresTable — readable project identity (FR-017a)", () => {
  test("a per-project store shows its directory basename + absolute path, not the ULID", () => {
    const store = makeStore({
      name: "project-01HXYZ00000000000000000000",
      scope: "project",
      project_id: "01HXYZ00000000000000000000",
      project_root: "/Users/me/code/coffer",
    });
    render(wrap(<MemoryStoresTable items={[store]} />));

    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("/Users/me/code/coffer")).toBeInTheDocument();
    // The opaque store name is never shown to the user as the label.
    expect(screen.queryByText("project-01HXYZ00000000000000000000")).not.toBeInTheDocument();
  });

  test("the global store reads as 'global'", () => {
    render(wrap(<MemoryStoresTable items={[makeStore()]} />));
    expect(screen.getByText("global")).toBeInTheDocument();
  });

  test("a project store with an unknown root falls back to the store name", () => {
    const store = makeStore({
      name: "project-01HUNTRACKED00000000000000",
      scope: "project",
      project_id: "01HUNTRACKED00000000000000",
      project_root: null,
    });
    render(wrap(<MemoryStoresTable items={[store]} />));
    expect(screen.getByText("project-01HUNTRACKED00000000000000")).toBeInTheDocument();
  });
});
