// frontend/src/pages/MemoryDetailPage.test.tsx
//
// Wiring smoke test for one partition's detail page: the way back, the header
// (name + project root), the reach control, and the file browser standing where
// the fact list used to. Data hooks are mocked, mirroring
// KnowledgeDetailPage.test.tsx.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { MemoryDetailPage } from "@/pages/MemoryDetailPage";

vi.mock("@/lib/hooks/useMemory", () => ({
  useMemoryPartitions: vi.fn(() => ({
    data: [{ name: "coffer", project_root: "/Users/dev/coffer", fact_count: 1 }],
  })),
  useOrganisePartition: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  // Mounted transitively via MemoryFileTree; this suite only exercises the
  // page's own wiring, so both file hooks get inert defaults.
  usePartitionFiles: vi.fn(() => ({
    data: {
      name: "coffer",
      path: "",
      abs_path: "/Users/dev/.coffer/memory/coffer",
      type: "dir",
      size: null,
      truncated: false,
      children: [
        {
          name: "MEMORY.md",
          path: "MEMORY.md",
          abs_path: "/Users/dev/.coffer/memory/coffer/MEMORY.md",
          type: "file",
          size: 10,
          truncated: false,
          children: null,
        },
      ],
    },
    isPending: false,
    error: null,
  })),
  usePartitionFileContent: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
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

function renderPage() {
  // ScopeControl reads the agent registry to build its pick-list, so the page
  // needs a query client.
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
  test("renders the partition's project root, reach control and its files", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "coffer" })).toBeInTheDocument();
    expect(screen.getByText("/Users/dev/coffer")).toBeInTheDocument();
    expect(screen.getByTestId("scope-control")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MEMORY\.md/ })).toBeInTheDocument();
  });

  test("offers the way back to the partitions list", () => {
    // A partition is reached by clicking a row, so leaving it must not depend
    // on the browser's own back button — every other detail page carries this.
    renderPage();

    expect(screen.getByRole("link", { name: /back to memory/i })).toBeInTheDocument();
  });
});
