// frontend/src/pages/MemoryDetailPage.test.tsx
//
// Wiring smoke test for one partition's detail page: the way back, the header
// (name + the repository it is keyed on, and whether that repository is still
// there), the status control, and the file browser standing where the fact list
// used to. Data hooks are mocked, mirroring KnowledgeDetailPage.test.tsx.
//
// Unlike the list, this page passes NO prefetched scope, so the control asks
// the server — and the `memory` kind answers `supports_scope: false`. That is
// the whole of how the per-agent panel disappears here: no prop, no special
// case on the page, just the answer honoured. The scope hook is stubbed with
// that answer so the test proves the page honours it rather than that someone
// remembered to pass a flag.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { MemoryDetailPage } from "@/pages/MemoryDetailPage";

// The page asks the DAEMON whether a distil pass is running (that is the
// whole point — a component's own pending flag dies on navigation), so the
// hook is mocked here the way every other data hook is.
vi.mock("@/lib/hooks/useUpkeep", () => ({ useUpkeepRunning: vi.fn(() => false) }));
vi.mock("@/lib/hooks/useMemory", () => ({
  useMemoryPartitions: vi.fn(),
  useDistilPartition: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
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
// The page is addressed by uid and gets the partition's LABEL from this read —
// the heading, and the name `/upkeep/runs` reports a pass under.
vi.mock("@/lib/hooks/useResources", () => ({
  useResource: vi.fn(() => ({
    data: { uid: "mp-be27", kind: "memory", name: "coffer", enabled: true, scope: null },
  })),
}));
const scopePut = vi.fn();
vi.mock("@/lib/hooks/useScope", () => ({
  // What the server answers for `memory`: no per-agent scope to set.
  useResourceScope: vi.fn(() => ({ data: { scope: null, supports_scope: false } })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: scopePut, isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
vi.mock("@/lib/hooks/useResourceMutations", () => {
  const stub = () => ({ mutate: vi.fn(), isPending: false });
  return { useEnableResource: vi.fn(stub), useDisableResource: vi.fn(stub) };
});

function renderPage() {
  // ScopeControl reads the agent registry to build its pick-list, so the page
  // needs a query client; the Distil button's Tooltip needs the provider the
  // app shell normally hosts, and the page is rendered bare here.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/memory/${PARTITION_UID}`]}>
          <Routes>
            <Route path="/memory/:uid" element={<MemoryDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const { useMemoryPartitions, useDistilPartition, usePartitionFiles } =
  await import("@/lib/hooks/useMemory");
const { useUpkeepRunning } = await import("@/lib/hooks/useUpkeep");
const partitionsMock = vi.mocked(useMemoryPartitions);
const runningMock = vi.mocked(useUpkeepRunning);
const distilMock = vi.mocked(useDistilPartition);
const filesMock = vi.mocked(usePartitionFiles);

/** The two identities the page holds apart: the uid the URL carries and every
 *  `/memory/partitions/{uid}/…` route takes, and the name the folder has — and
 *  which is therefore what a running pass is reported under. */
const PARTITION_UID = "mp-be27";
const PARTITION_NAME = "coffer";

const COFFER: PartitionOut = {
  uid: PARTITION_UID,
  name: PARTITION_NAME,
  repository_path: "/Users/dev/coffer",
  repository_key: "remote:github.com/wyx-sg/coffer",
  note_count: 1,
  unresolvable: false,
};

function stubPartitions(partitions: PartitionOut[]) {
  partitionsMock.mockReturnValue({
    data: partitions,
  } as unknown as ReturnType<typeof useMemoryPartitions>);
}

describe("MemoryDetailPage", () => {
  beforeEach(() => {
    runningMock.mockReturnValue(false);
    stubPartitions([COFFER]);
  });

  test("renders the repository it is keyed on, the status control and its files", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "coffer" })).toBeInTheDocument();
    expect(screen.getByText("/Users/dev/coffer")).toBeInTheDocument();
    expect(screen.getByTestId("scope-control")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MEMORY\.md/ })).toBeInTheDocument();
  });

  test("the header control offers no per-agent reach, because the server has none", () => {
    renderPage();
    const control = within(screen.getByTestId("scope-control")).getByRole("button");
    // Its label is the state, and the state is just "served or not".
    expect(control).toHaveTextContent(/^enabled$/i);

    fireEvent.click(control);
    expect(screen.queryByRole("radio", { name: /only selected/i })).toBeNull();
    expect(screen.queryByRole("radio", { name: /every agent/i })).toBeNull();
    expect(screen.getByRole("radio", { name: /^enabled$/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^disabled$/i })).toBeInTheDocument();
    // And nothing here ever PUTs a scope the server would refuse.
    expect(scopePut).not.toHaveBeenCalled();
  });

  test("a partition whose repository is gone says so in its header", () => {
    // FR-016: nothing is delivered from it, and whether it should still exist
    // is the developer's call — which they can only make if the page says so.
    stubPartitions([{ ...COFFER, unresolvable: true }]);

    renderPage();

    expect(screen.getByTestId("partition-unresolvable-badge")).toHaveTextContent(
      /repository missing/i,
    );
  });

  test("a resolvable partition carries no such mark", () => {
    renderPage();
    expect(screen.queryByTestId("partition-unresolvable-badge")).toBeNull();
  });

  test("spins the Distil button while a pass this page did not start is running", () => {
    // The bug: the spinner used to come from the mutation's own `isPending`,
    // which a remount resets — so leaving the page mid-pass and coming back
    // showed an idle button and invited a second concurrent rewrite. The
    // running state is the daemon's answer now, so `isPending: false` and a
    // running pass must still read as running.
    runningMock.mockReturnValue(true);

    renderPage();

    const button = screen.getByRole("button", { name: /distil/i });
    expect(button).toBeDisabled();
    expect(button.querySelector(".animate-spin")).not.toBeNull();
  });

  test("the Distil button is idle when nothing is running", () => {
    renderPage();

    const button = screen.getByRole("button", { name: /distil/i });
    expect(button).not.toBeDisabled();
    expect(button.querySelector(".animate-spin")).toBeNull();
  });

  test("the uid addresses the partition; its name is what a running pass is named by", () => {
    // Both routes under this page take the uid, and `/upkeep/runs` reports the
    // folder being rewritten — which is named after the partition. So the page
    // has to hold both, and this is the assertion that it does.
    renderPage();

    expect(distilMock).toHaveBeenCalledWith(PARTITION_UID);
    expect(filesMock).toHaveBeenCalledWith(PARTITION_UID);
    expect(runningMock).toHaveBeenCalledWith("memory", PARTITION_NAME);
  });

  test("offers the way back to the partitions list", () => {
    // A partition is reached by clicking a row, so leaving it must not depend
    // on the browser's own back button — every other detail page carries this.
    renderPage();

    expect(screen.getByRole("link", { name: /back to memory/i })).toBeInTheDocument();
  });
});
