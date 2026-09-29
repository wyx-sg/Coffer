// frontend/src/pages/MemoryDetailPage.test.tsx
//
// Wiring smoke test for one partition's detail page: the way back, the header
// (name + the repository it is keyed on, and whether that repository is still
// there), the one Update memory button, and the file browser. No status or
// reach control: every partition is served to every agent. Data hooks are
// mocked, mirroring KnowledgeDetailPage.test.tsx.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { MemoryDetailPage } from "@/pages/MemoryDetailPage";
import { acceptance } from "@/test/acceptance";

// The page asks the DAEMON whether a distil pass is running (that is the
// whole point — a component's own pending flag dies on navigation), so the
// hook is mocked here the way every other data hook is.
vi.mock("@/lib/hooks/useUpkeep", () => ({ useUpkeepRunning: vi.fn(() => false) }));
const updateMutate = vi.fn();
vi.mock("@/lib/hooks/useMemory", () => ({
  useMemoryPartitions: vi.fn(),
  useSyncMemory: vi.fn(() => ({ mutate: updateMutate, isPending: false })),
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
// The header's Edit dialog sets the partition's title.
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useSetResourceTitle: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    reset: vi.fn(),
    error: null,
  })),
}));

function renderPage() {
  // The Update memory button's Tooltip needs the provider the app shell
  // normally hosts, and the page is rendered bare here.
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

const { useMemoryPartitions, usePartitionFiles } = await import("@/lib/hooks/useMemory");
const { useUpkeepRunning } = await import("@/lib/hooks/useUpkeep");
const partitionsMock = vi.mocked(useMemoryPartitions);
const runningMock = vi.mocked(useUpkeepRunning);
const filesMock = vi.mocked(usePartitionFiles);

/** The two identities the page holds apart: the uid the URL carries and every
 *  `/memory/partitions/{uid}/…` route takes, and the name the folder has — and
 *  which is therefore what a running pass is reported under. */
const PARTITION_UID = "mp-be27";
const PARTITION_NAME = "coffer";

const COFFER: PartitionOut = {
  uid: PARTITION_UID,
  name: PARTITION_NAME,
  title: null,
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
    updateMutate.mockClear();
    stubPartitions([COFFER]);
  });

  test("renders the repository it is keyed on and its files", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "coffer" })).toBeInTheDocument();
    expect(screen.getByText("/Users/dev/coffer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MEMORY\.md/ })).toBeInTheDocument();
  });

  acceptance("web-ui", "a kind that cannot be disabled shows no status control", () => {
    // The partition's page half: no reach or status button in the header.
    renderPage();
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(enabled|disabled|every agent)$/i })).toBeNull();
  });

  test("one Update memory button, and no separate Distil or Read action", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /update memory/i }));
    expect(updateMutate).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /distil/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /read from agents/i })).toBeNull();
  });

  test("a partition whose repository is gone says so in its header", () => {
    // "Report unresolvable partitions": nothing is delivered from it, and whether it should still
    // exist is the developer's call — which they can only make if the page says so.
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

  test("spins the Update button while a pass this page did not start is running", () => {
    // The bug: the spinner used to come from the mutation's own `isPending`,
    // which a remount resets — so leaving the page mid-pass and coming back
    // showed an idle button and invited a second concurrent rewrite. The
    // running state is the daemon's answer now, so `isPending: false` and a
    // running pass must still read as running.
    runningMock.mockReturnValue(true);

    renderPage();

    const button = screen.getByRole("button", { name: /updating/i });
    expect(button).toBeDisabled();
    expect(button.querySelector(".animate-spin")).not.toBeNull();
  });

  test("the Update button is idle when nothing is running", () => {
    renderPage();

    const button = screen.getByRole("button", { name: /update memory/i });
    expect(button).not.toBeDisabled();
    expect(button.querySelector(".animate-spin")).toBeNull();
  });

  test("the uid addresses the partition; its name is what a running pass is named by", () => {
    // The file routes take the uid, and `/upkeep/runs` reports the folder
    // being rewritten — which is named after the partition. So the page has to
    // hold both, and this is the assertion that it does.
    renderPage();

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
