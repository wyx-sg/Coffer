// frontend/src/pages/sync/SyncHistoryTab.test.tsx
//
// The History tab replaced the single "Last round" card, so what it has to
// prove is everything that card could not: that a round other than the newest
// is visible at all, that applied and published stay two separate numbers, and
// that the rounds which changed nothing are listed too — they are what makes a
// gap in the record visible rather than an idle-looking vault.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { RunRecord } from "@/lib/api/sync";
import { SyncHistoryTab } from "./SyncHistoryTab";

vi.mock("@/lib/hooks/useSync", () => ({ useSyncRuns: vi.fn() }));

const { useSyncRuns } = await import("@/lib/hooks/useSync");

const NO_COUNTS = { added: 0, modified: 0, deleted: 0 };

function run(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id: 1,
    started_at: "2026-09-13T09:00:00Z",
    finished_at: "2026-09-13T09:00:04Z",
    status: "ok",
    join: null,
    applied: NO_COUNTS,
    published: NO_COUNTS,
    commit: null,
    conflicts: [],
    agent_resolved: [],
    failures: [],
    locked_refs: [],
    pending: null,
    error: null,
    ...overrides,
  };
}

function seed(runs: RunRecord[], state: { isLoading?: boolean; error?: unknown } = {}) {
  vi.mocked(useSyncRuns).mockReturnValue({
    data: state.isLoading || state.error ? undefined : { runs },
    isLoading: Boolean(state.isLoading),
    error: state.error ?? null,
  } as unknown as ReturnType<typeof useSyncRuns>);
}

/** The table's data rows, skipping the header. */
function rows() {
  return screen.getAllByRole("row").slice(1);
}

afterEach(() => vi.clearAllMocks());

describe("SyncHistoryTab", () => {
  test("lists every round, not just the last one", () => {
    seed([
      run({ id: 3, commit: "ccc3333333" }),
      run({ id: 2, commit: "bbb2222222" }),
      run({ id: 1, commit: "aaa1111111" }),
    ]);
    render(<SyncHistoryTab enabled />);

    expect(rows()).toHaveLength(3);
    expect(screen.getByText("aaa1111111")).toBeInTheDocument();
  });

  test("keeps what a round applied here and what it published apart", () => {
    // The whole point of bidirectional convergence: a machine that publishes
    // every round and applies nothing is coming FROM somewhere, and one that
    // applies and never publishes is going TO somewhere. One merged number
    // would hide both.
    seed([
      run({
        applied: { added: 0, modified: 0, deleted: 0 },
        published: { added: 322, modified: 0, deleted: 0 },
      }),
    ]);
    render(<SyncHistoryTab enabled />);

    const cells = within(rows()[0]).getAllByRole("cell");
    // [expander, when, outcome, applied, published, commit]
    expect(cells[3]).toHaveTextContent("0");
    expect(cells[4]).toHaveTextContent("322");
  });

  test("a round that changed nothing is still a row", () => {
    seed([run({ status: "no_change" }), run({ id: 2, status: "ok" })]);
    render(<SyncHistoryTab enabled />);
    expect(rows()).toHaveLength(2);
    expect(screen.getByText(/nothing changed/i)).toBeInTheDocument();
  });

  test("a round that landed no commit says so rather than showing a blank", () => {
    seed([run({ status: "no_change", commit: null })]);
    render(<SyncHistoryTab enabled />);
    expect(within(rows()[0]).getAllByRole("cell")[5]).toHaveTextContent("—");
  });

  test("a join is marked, because the same counts mean something else on it", () => {
    seed([run({ join: "new", published: { added: 322, modified: 0, deleted: 0 } })]);
    render(<SyncHistoryTab enabled />);
    expect(screen.getByText(/joined as new/i)).toBeInTheDocument();
  });

  test("opening a round shows what the row could not carry", () => {
    seed([
      run({
        status: "push_failed",
        agent_resolved: ["knowledge/notes/merged.md"],
        failures: [{ path: "resources/agent/desktop.yaml", reason: "config_dir missing" }],
        locked_refs: ["github.TOKEN"],
        error: "remote rejected the push",
      }),
    ]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(rows()[0]);
    expect(screen.getByTestId("sync-run-agent-resolved")).toHaveTextContent(
      "knowledge/notes/merged.md",
    );
    expect(screen.getByTestId("sync-run-failures")).toHaveTextContent("config_dir missing");
    expect(screen.getByTestId("sync-run-locked-refs")).toHaveTextContent("github.TOKEN");
    expect(screen.getByRole("alert")).toHaveTextContent("remote rejected the push");
  });

  test("the outcome filter narrows to the rounds that went wrong", () => {
    seed([
      run({ id: 1, status: "no_change" }),
      run({ id: 2, status: "failed", commit: null, error: "network unreachable" }),
    ]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(screen.getByRole("combobox", { name: /outcome/i }));
    fireEvent.click(screen.getByRole("option", { name: /^failed$/i }));

    expect(rows()).toHaveLength(1);
    expect(screen.queryByText(/nothing changed/i)).not.toBeInTheDocument();
  });

  test("an empty history says so instead of rendering an empty table", () => {
    seed([]);
    render(<SyncHistoryTab enabled />);
    expect(screen.getByText(/no round has run yet/i)).toBeInTheDocument();
  });

  test("a daemon that cannot serve the history fails inside this tab", () => {
    // An older daemon has no /sync/runs route. That must not blank Status or
    // Machines, so the error is rendered here rather than thrown upward.
    seed([], { error: new Error("Not Found") });
    render(<SyncHistoryTab enabled />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
