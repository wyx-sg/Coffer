// frontend/src/kinds/memory/MemoryMergeDialog.test.tsx
//
// The AI merge dialog: scans on open, renders proposals with confidence +
// judged-by + reason, merges in the shown direction (swap flips it), shows
// the no-model hint, and reports "no candidates" for an empty scan.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryMergeDialog } from "./MemoryMergeDialog";
import type { MergeProposalOut } from "./types";

vi.mock("./api", () => ({ mergeScanMemoryStores: vi.fn(), mergeMemoryStores: vi.fn() }));
const api = await import("./api");

const _A = "project-" + "A".repeat(26);
const _B = "project-" + "B".repeat(26);

const PROPOSAL: MergeProposalOut = {
  source: _B,
  target: _A,
  confidence: "high",
  judged_by: "engine",
  reason: "same fact titles",
  source_evidence: {
    store: _B,
    label: "Old Machine",
    root: "/old/repo",
    remote: null,
    facts: 2,
  },
  target_evidence: {
    store: _A,
    label: null,
    root: "/new/coffer",
    remote: "github.com/u/coffer",
    facts: 7,
  },
};

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryMergeDialog open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("MemoryMergeDialog", () => {
  test("scans on open and renders the proposal with reason and confidence", async () => {
    vi.mocked(api.mergeScanMemoryStores).mockResolvedValue({
      engine: "ok",
      truncated: false,
      proposals: [PROPOSAL],
    });
    renderDialog();
    expect(await screen.findByText(/same fact titles/)).toBeInTheDocument();
    expect(screen.getByText("Old Machine")).toBeInTheDocument(); // label wins
    expect(screen.getByText("coffer")).toBeInTheDocument(); // root basename fallback
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(api.mergeScanMemoryStores).toHaveBeenCalledTimes(1);
  });

  test("merge sends the shown direction and drops the proposal on success", async () => {
    vi.mocked(api.mergeScanMemoryStores).mockResolvedValue({
      engine: "ok",
      truncated: false,
      proposals: [PROPOSAL],
    });
    vi.mocked(api.mergeMemoryStores).mockResolvedValue({
      target: _A,
      merged_files: 2,
      label_moved: true,
      root_moved: false,
      aliases: ["B".repeat(26)],
      reorg_status: "no_model",
    });
    renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: /^merge$/i }));
    await waitFor(() => expect(api.mergeMemoryStores).toHaveBeenCalledWith(_B, _A));
    expect(await screen.findByText(/no merge candidates/i)).toBeInTheDocument();
  });

  test("swap flips the merge direction", async () => {
    vi.mocked(api.mergeScanMemoryStores).mockResolvedValue({
      engine: "ok",
      truncated: false,
      proposals: [PROPOSAL],
    });
    vi.mocked(api.mergeMemoryStores).mockResolvedValue({
      target: _B,
      merged_files: 1,
      label_moved: false,
      root_moved: false,
      aliases: ["A".repeat(26)],
      reorg_status: "skipped",
    });
    renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: /swap direction/i }));
    fireEvent.click(screen.getByRole("button", { name: /^merge$/i }));
    await waitFor(() => expect(api.mergeMemoryStores).toHaveBeenCalledWith(_A, _B));
  });

  test("a swap set on one proposal survives another proposal's merge", async () => {
    // Review regression: swap state keyed by array index attached to the WRONG
    // pair after a merge filtered the list; it must stay with its pair.
    const _C = "project-" + "C".repeat(26);
    const _D = "project-" + "D".repeat(26);
    const second: MergeProposalOut = {
      ...PROPOSAL,
      source: _D,
      target: _C,
      source_evidence: { store: _D, label: null, root: null, remote: null, facts: 1 },
      target_evidence: { store: _C, label: null, root: null, remote: null, facts: 5 },
    };
    vi.mocked(api.mergeScanMemoryStores).mockResolvedValue({
      engine: "ok",
      truncated: false,
      proposals: [PROPOSAL, second],
    });
    vi.mocked(api.mergeMemoryStores).mockResolvedValue({
      target: _A,
      merged_files: 1,
      label_moved: false,
      root_moved: false,
      aliases: [],
      reorg_status: "skipped",
    });
    renderDialog();
    // Swap the SECOND proposal (C/D), then merge the FIRST (A/B).
    const swaps = await screen.findAllByRole("button", { name: /swap direction/i });
    fireEvent.click(swaps[1]);
    fireEvent.click(screen.getAllByRole("button", { name: /^merge$/i })[0]);
    await waitFor(() => expect(api.mergeMemoryStores).toHaveBeenCalledWith(_B, _A));
    // The remaining proposal must still honor ITS swap: C → D (not D → C).
    fireEvent.click(await screen.findByRole("button", { name: /^merge$/i }));
    await waitFor(() => expect(api.mergeMemoryStores).toHaveBeenLastCalledWith(_C, _D));
  });

  test("no_model scan shows the configure-engine hint", async () => {
    vi.mocked(api.mergeScanMemoryStores).mockResolvedValue({
      engine: "no_model",
      truncated: false,
      proposals: [],
    });
    renderDialog();
    expect(await screen.findByText(/no internal engine is configured/i)).toBeInTheDocument();
    expect(screen.getByText(/no merge candidates/i)).toBeInTheDocument();
  });
});
