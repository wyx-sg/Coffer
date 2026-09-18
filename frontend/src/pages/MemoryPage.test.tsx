// frontend/src/pages/MemoryPage.test.tsx
//
// The Memory page is a list page and must read as one (spec memory FR-037):
// a table, in the same shape whether the vault holds partitions or none, and
// nothing else. Two surfaces that used to render above and below that table
// are asserted ABSENT here, because both were duplicates of somewhere better:
// per-agent delivery now lives on the agent's own detail page (it writes that
// agent's settings file), and the audit log is the Activity page's Changes
// tab, which reads the whole vault's trail rather than one kind's slice.
import { describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { MemoryPage } from "./MemoryPage";
import type { PartitionOut } from "@/lib/api/memoryTypes";

vi.mock("@/lib/hooks/useMemory", () => ({
  memoryKey: ["memory"],
  useMemoryPartitions: vi.fn(),
  useSyncMemory: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useResources", () => ({ useResources: vi.fn(() => ({ data: [] })) }));
// ScopeControl's own network hooks — only reached once a row renders.
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "claude_code" }] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => {
  const stub = () => ({ mutate: vi.fn(), isPending: false });
  return { useEnableResource: vi.fn(stub), useDisableResource: vi.fn(stub) };
});

const { useMemoryPartitions } = await import("@/lib/hooks/useMemory");
const partitionsMock = vi.mocked(useMemoryPartitions);

function stubPartitions(partitions: PartitionOut[]) {
  partitionsMock.mockReturnValue({
    data: partitions,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useMemoryPartitions>);
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>
          <MemoryPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const COFFER: PartitionOut = {
  name: "coffer",
  repository_path: "/Users/dev/coffer",
  repository_key: "remote:github.com/wyx-sg/coffer",
  note_count: 34,
  unresolvable: false,
};

/** A partition whose repository has been deleted from disk (FR-016). */
const GONE: PartitionOut = {
  name: "old-api",
  repository_path: "/Users/dev/old-api",
  repository_key: "path:/Users/dev/old-api",
  note_count: 3,
  unresolvable: true,
};

describe("MemoryPage", () => {
  test("an empty vault gets the welcome every other first-run surface gives", () => {
    // Skills, knowledge, agents, channels and providers all greet a developer
    // who has nothing yet; Memory showing a bare table instead made it the one
    // page that explained itself least at the moment it mattered most.
    stubPartitions([]);
    renderPage();

    expect(screen.getByText("Nothing distilled yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    // The one next step is READ, not Add — nothing here is user-created — and
    // it is offered once, not twice.
    expect(screen.getAllByRole("button", { name: /Read from agents/i })).toHaveLength(1);
  });

  test("once a partition exists the page is the table", () => {
    stubPartitions([COFFER]);
    renderPage();

    const table = screen.getByRole("table");
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual(expect.arrayContaining(["Partition", "Repository", "Notes", "Reach"]));
  });

  test("the read-from-agents affordance stays reachable from the empty state", () => {
    // Reading the agents' memory is the only way to populate the page, so
    // losing it with the empty-state card would have been a dead end. It is
    // not called Sync — that name is the vault-sync page's.
    stubPartitions([]);
    renderPage();
    expect(screen.getByRole("button", { name: /read from agents/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sync$/i })).toBeNull();
  });

  test("partitions render as rows of that same table", () => {
    stubPartitions([COFFER]);
    renderPage();

    const table = screen.getByRole("table");
    expect(within(table).getByText("coffer")).toBeInTheDocument();
    expect(within(table).getByText("/Users/dev/coffer")).toBeInTheDocument();
    expect(within(table).getByText("34")).toBeInTheDocument();
  });

  test("a partition whose repository is gone is listed, not hidden", () => {
    // FR-016: it is delivered to nobody, and only the developer can decide
    // whether to delete it — which they cannot do from a list it is missing
    // from. So it is on the page, marked.
    stubPartitions([COFFER, GONE]);
    renderPage();

    const table = screen.getByRole("table");
    expect(within(table).getByText("old-api")).toBeInTheDocument();
    expect(within(table).getByTestId("partition-unresolvable-badge")).toBeInTheDocument();
  });

  test("no audit-log section — the Activity page holds the vault's whole trail", () => {
    stubPartitions([COFFER]);
    renderPage();

    expect(screen.queryByTestId("memory-audit-log")).toBeNull();
    expect(screen.queryByText(/audit log/i)).toBeNull();
  });

  test("no delivery section — delivery is per-agent, so it lives on the agent page", () => {
    stubPartitions([COFFER]);
    renderPage();

    expect(screen.queryByText(/^delivery$/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /install/i })).toBeNull();
  });
});
