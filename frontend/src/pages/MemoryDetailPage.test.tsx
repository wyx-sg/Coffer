// frontend/src/pages/MemoryDetailPage.test.tsx
//
// Wiring smoke test for one partition's detail page: header + reach control,
// the conflicts panel, and the fact list all render from the same facts
// query. Data hooks are mocked, mirroring KnowledgeDetailPage.test.tsx.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { MemoryDetailPage } from "./MemoryDetailPage";
import type { FactSummaryOut } from "@/lib/api/memoryTypes";

vi.mock("@/lib/hooks/useMemory", () => ({
  useMemoryFacts: vi.fn(),
  useMemoryOverrides: vi.fn(() => ({ data: [] })),
  useMemoryPartitions: vi.fn(() => ({
    data: [{ name: "coffer", project_root: "/Users/dev/coffer", fact_count: 1 }],
  })),
  useOrganisePartition: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  // Mounted transitively via MemoryConflictsPanel / MemoryFactCard; this
  // suite only exercises the page's own wiring, so both get inert defaults.
  useSetOverride: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useClearOverride: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useMemoryFact: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
}));
vi.mock("@/lib/hooks/useResources", () => ({
  useResource: vi.fn(() => ({ data: { enabled: true, scope: null } })),
}));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
vi.mock("@/lib/hooks/useResourceMutations", () => {
  const stub = () => ({ mutate: vi.fn(), isPending: false });
  return { useEnableResource: vi.fn(stub), useDisableResource: vi.fn(stub) };
});

const { useMemoryFacts } = await import("@/lib/hooks/useMemory");
const factsMock = vi.mocked(useMemoryFacts);

const FACTS: FactSummaryOut[] = [
  {
    key: "a",
    slug: "a",
    partition: "coffer",
    title: "Develop in a worktree",
    description: "This repository must be developed in a git worktree.",
    type: "project",
    status: "active",
    superseded_by: "",
    conflicts_with: [],
    proposed: false,
    hidden: false,
    pinned: false,
  },
];

function renderPage() {
  // ScopeControl reads the machine registry to build its pick-list (scope's
  // machine axis, spec vault-sync), so the page needs a query client.
  // The header's Organise button carries a tooltip, which Layout's provider
  // normally hosts; the page is rendered bare here, so mount one.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/memory/coffer"]}>
          <Routes>
            <Route path="/memory/:name" element={<MemoryDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("MemoryDetailPage", () => {
  test("renders the partition's project root, reach control and facts", () => {
    factsMock.mockReturnValue({
      data: FACTS,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useMemoryFacts>);

    renderPage();

    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("/Users/dev/coffer")).toBeInTheDocument();
    expect(screen.getByTestId("scope-control")).toBeInTheDocument();
    expect(screen.getByText("Develop in a worktree")).toBeInTheDocument();
  });

  test("offers the way back to the partitions list", () => {
    // A partition is reached by clicking a row, so leaving it must not depend
    // on the browser's own back button — every other detail page carries this.
    factsMock.mockReturnValue({
      data: FACTS,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useMemoryFacts>);

    renderPage();

    expect(screen.getByRole("link", { name: /back to memory/i })).toBeInTheDocument();
  });
});
