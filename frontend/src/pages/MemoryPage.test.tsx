// frontend/src/pages/MemoryPage.test.tsx
//
// The Memory page is a list page and must read as one (spec memory "Present
// partitions as a table and a file tree"):
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
import { acceptance } from "@/test/acceptance";
import type { PartitionOut } from "@/lib/api/memoryTypes";

vi.mock("@/lib/hooks/useMemory", () => ({
  memoryKey: ["memory"],
  useMemoryPartitions: vi.fn(),
  useSyncMemory: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
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
  uid: "mp-be27",
  name: "coffer",
  title: null,
  repository_path: "/Users/dev/coffer",
  repository_key: "remote:github.com/wyx-sg/coffer",
  note_count: 34,
  unresolvable: false,
};

/** A partition whose repository has been deleted from disk (see "Report
 *  unresolvable partitions"). */
const GONE: PartitionOut = {
  uid: "mp-0d5c",
  name: "old-api",
  title: null,
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
    // The one next step is UPDATE, not Add — nothing here is user-created —
    // and it is offered once, not twice.
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(1);
  });

  test("once a partition exists the page is the table", () => {
    stubPartitions([COFFER]);
    renderPage();

    const table = screen.getByRole("table");
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    // No Status or Reach column: every partition is served to every agent.
    expect(headers).toEqual(expect.arrayContaining(["Partition", "Repository", "Notes"]));
    expect(headers).not.toContain("Status");
    expect(headers).not.toContain("Reach");
  });

  test("the update affordance stays reachable from the empty state", () => {
    // Updating memory is the only way to populate the page, so losing it with
    // the empty-state card would have been a dead end. It is not called Sync —
    // that name is the vault-sync page's.
    stubPartitions([]);
    renderPage();
    expect(screen.getByRole("button", { name: /update memory/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sync$/i })).toBeNull();
  });

  test("the populated page carries the same one Update memory button", () => {
    stubPartitions([COFFER]);
    renderPage();
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /read from agents/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /distil/i })).toBeNull();
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
    // "Report unresolvable partitions": it is delivered to nobody, and only the developer can
    // decide whether to delete it — which they cannot do from a list it is missing
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

acceptance("memory", "browse a partition as a file tree with a read-only preview", () => {
  // The partitions page's half: the first-run welcome with none, the table with one.
  stubPartitions([]);
  const { unmount } = renderPage();
  expect(screen.getByText("Nothing distilled yet")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  unmount();

  stubPartitions([COFFER]);
  renderPage();
  expect(screen.getByRole("table")).toBeInTheDocument();
});
