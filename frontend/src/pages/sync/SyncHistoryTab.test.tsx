// frontend/src/pages/sync/SyncHistoryTab.test.tsx
//
// The History tab replaced the single "Last round" card, so what it has to
// prove is everything that card could not: that a round other than the newest
// is visible at all, that applied and published stay two separate numbers, and
// that the rounds which changed nothing are listed too — they are what makes a
// gap in the record visible rather than an idle-looking vault.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import type { RunRecord } from "@/lib/api/sync";
import { SyncHistoryTab } from "./SyncHistoryTab";

vi.mock("@/lib/hooks/useSync", () => ({ useSyncRuns: vi.fn(), useRollbackRound: vi.fn() }));

const { useSyncRuns, useRollbackRound } = await import("@/lib/hooks/useSync");

const NO_COUNTS = { added: 0, modified: 0, deleted: 0, changes: [] };

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

/**
 * The rollback mutation, stubbed. `mutate` does nothing unless a test hands it
 * an implementation — the default is the failure case the dialog has to
 * survive: a click that never reports success must leave the dialog up.
 */
function seedRollback(
  overrides: { mutate?: ReturnType<typeof vi.fn>; isPending?: boolean; error?: unknown } = {},
) {
  const mutate = overrides.mutate ?? vi.fn();
  vi.mocked(useRollbackRound).mockReturnValue({
    mutate,
    isPending: overrides.isPending ?? false,
    error: overrides.error ?? null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useRollbackRound>);
  return mutate;
}

/** The table's data rows, skipping the header. */
function rows() {
  return screen.getAllByRole("row").slice(1);
}

/** The one "Undo this round" button a history table offers, if it offers one. */
function undoButtons() {
  return screen.queryAllByRole("button", { name: /undo this round/i });
}

beforeEach(() => seedRollback());

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
        applied: { added: 0, modified: 0, deleted: 0, changes: [] },
        published: { added: 322, modified: 0, deleted: 0, changes: [] },
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
    seed([run({ join: "new", published: { added: 322, modified: 0, deleted: 0, changes: [] } })]);
    render(<SyncHistoryTab enabled />);
    expect(screen.getByText(/joined as new/i)).toBeInTheDocument();
  });

  test("opening a round names the documents it moved", () => {
    // The row carries "+1 ~1"; this is the question that raises. Before, the
    // detail skipped straight to the faults and told a round that changed two
    // documents there was "nothing further to report" — while the paths sat in
    // the stored payload the whole time.
    seed([
      run({
        applied: {
          added: 0,
          modified: 1,
          deleted: 0,
          changes: [{ path: "knowledge/notes/a.md", status: "modified" }],
        },
        published: {
          added: 1,
          modified: 1,
          deleted: 0,
          changes: [
            { path: "resources/channel/seatalk.yaml", status: "added" },
            { path: "state/agent-plugins/codex.yaml", status: "modified" },
          ],
        },
      }),
    ]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(rows()[0]);
    expect(screen.getByTestId("sync-run-applied")).toHaveTextContent("knowledge/notes/a.md");
    expect(screen.getByTestId("sync-run-published")).toHaveTextContent(
      "resources/channel/seatalk.yaml",
    );
    expect(screen.getByTestId("sync-run-published")).toHaveTextContent(
      "state/agent-plugins/codex.yaml",
    );
    // …and it no longer claims there is nothing to say.
    expect(screen.queryByText(/nothing further/i)).toBeNull();
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

// `POST /sync/rollback` undoes ONE round — the one that left the newest
// pre-apply snapshot — so the button may appear on exactly one row, and only
// on the row whose round that is. An "Undo" on every row would be a lie: every
// one of them would undo the same, most recent round.
describe("SyncHistoryTab — undoing a round", () => {
  const APPLIED = {
    added: 1,
    modified: 1,
    deleted: 0,
    changes: [
      { path: "knowledge/notes/a.md", status: "added" as const },
      { path: "resources/channel/seatalk.yaml", status: "modified" as const },
    ],
  };

  test("offers the undo on exactly one round — the one a rollback would undo", () => {
    seed([run({ id: 3, applied: APPLIED }), run({ id: 2 }), run({ id: 1 })]);
    render(<SyncHistoryTab enabled />);

    expect(undoButtons()).toHaveLength(1);
    expect(within(rows()[0]).getByRole("button", { name: /undo this round/i })).toBeInTheDocument();
  });

  test("looks past a round that never reached the snapshot to the one that did", () => {
    // A conflicted round stops at the merge, before the snapshot step: the
    // newest snapshot — and so the round a rollback undoes — is the `ok` one
    // underneath it.
    seed([run({ id: 3, status: "conflict", conflicts: ["knowledge/notes/a.md"] }), run({ id: 2 })]);
    render(<SyncHistoryTab enabled />);

    expect(undoButtons()).toHaveLength(1);
    expect(within(rows()[1]).getByRole("button", { name: /undo this round/i })).toBeInTheDocument();
  });

  test("offers no undo when the newest round's status cannot say where it stopped", () => {
    // A `failed` round may have died before the snapshot or after it. Naming
    // the round underneath as the one that gets undone would be a guess, and
    // the wrong guess reverses a round the user did not point at.
    seed([run({ id: 3, status: "failed", error: "network unreachable" }), run({ id: 2 })]);
    render(<SyncHistoryTab enabled />);

    expect(undoButtons()).toHaveLength(0);
  });

  test("the confirmation names the round and the documents it would take back", () => {
    seed([run({ id: 3, applied: APPLIED })]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(undoButtons()[0]);
    const dialog = screen.getByRole("dialog");
    // The round: by the time it finished, which is how every other surface
    // names a round.
    expect(dialog).toHaveTextContent(/2026/);
    // What it touched: the paths the row already carries, not a count alone.
    expect(dialog).toHaveTextContent("knowledge/notes/a.md");
    expect(dialog).toHaveTextContent("resources/channel/seatalk.yaml");
  });

  test("a round that applied nothing here says so instead of listing nothing", () => {
    seed([run({ id: 3, status: "no_change" })]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(undoButtons()[0]);
    expect(screen.getByRole("dialog")).toHaveTextContent(/applied nothing/i);
  });

  test("a failed undo keeps the dialog open with the reason", () => {
    // The convention every destructive action here follows: the dialog closes
    // only on success, so a rollback the daemon refused is readable and
    // retryable instead of vanishing as if it had worked.
    const mutate = seedRollback({
      error: new ApiError("SYNC_NOTHING_TO_ROLL_BACK", "no pre-apply snapshot to roll back to"),
    });
    seed([run({ id: 3, applied: APPLIED })]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(undoButtons()[0]);
    fireEvent.click(screen.getByRole("button", { name: /^undo round$/i }));

    expect(mutate).toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // Translated from the error CODE (`errors.SYNC_NOTHING_TO_ROLL_BACK`),
    // not the daemon's raw sentence — every failure on this surface reads the
    // same way.
    expect(screen.getByRole("alert")).toHaveTextContent(/no round to roll back to/i);
  });

  test("the dialog closes once the rollback succeeds", () => {
    const mutate = seedRollback({
      mutate: vi.fn((_vars: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.()),
    });
    seed([run({ id: 3, applied: APPLIED })]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(undoButtons()[0]);
    fireEvent.click(screen.getByRole("button", { name: /^undo round$/i }));

    expect(mutate).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("the undo does not double as the row's expander", () => {
    // The row opens its detail on click; a button inside it that let the click
    // through would open the detail behind the dialog it just raised.
    seed([run({ id: 3, applied: APPLIED })]);
    render(<SyncHistoryTab enabled />);

    fireEvent.click(undoButtons()[0]);
    expect(screen.queryByTestId("sync-run-applied")).toBeNull();
  });
});
