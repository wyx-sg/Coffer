// frontend/src/pages/sync/SyncRunsTab.test.tsx
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
import { formatDateTime } from "@/lib/utils";
import { SyncRunsTab } from "./SyncRunsTab";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncRuns: vi.fn(),
  useRollbackRound: vi.fn(),
  // The tab reads the vault's CURRENT pending state, which the history cannot
  // answer: a row keeps `awaiting_confirmation` after the situation is
  // answered, so only this says whether anything is still waiting.
  useSyncStatus: vi.fn(),
  // Reached through the held-round actions on whichever row is waiting.
  useConfirmRound: vi.fn(),
  useRejectRound: vi.fn(),
  useRebuildFromRemote: vi.fn(),
}));

const {
  useSyncRuns,
  useRollbackRound,
  useSyncStatus,
  useConfirmRound,
  useRejectRound,
  useRebuildFromRemote,
} = await import("@/lib/hooks/useSync");

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

const idleMutation = () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() });

/** The vault at rest: nothing held, no conflict. Tests that want a held round
 *  override it — and that is the only way to get the held-round answers onto a
 *  row, which is the point. */
function seedStatus(over: Record<string, unknown> = {}) {
  (useSyncStatus as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    data: { last_run: { pending: null, conflicts: [] }, remote: null, ...over },
  } as unknown as ReturnType<typeof useSyncStatus>);
}

beforeEach(() => {
  seedRollback();
  seedStatus();
  for (const hook of [useConfirmRound, useRejectRound, useRebuildFromRemote]) {
    (hook as unknown as ReturnType<typeof vi.fn>).mockReturnValue(idleMutation());
  }
});

afterEach(() => vi.clearAllMocks());

describe("SyncRunsTab", () => {
  test("lists every round, not just the last one", () => {
    seed([
      run({ id: 3, commit: "ccc3333333" }),
      run({ id: 2, commit: "bbb2222222" }),
      run({ id: 1, commit: "aaa1111111" }),
    ]);
    render(<SyncRunsTab enabled />);

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
    render(<SyncRunsTab enabled />);

    const cells = within(rows()[0]).getAllByRole("cell");
    // [expander, when, outcome, applied, published, commit]
    expect(cells[3]).toHaveTextContent("0");
    expect(cells[4]).toHaveTextContent("322");
  });

  test("a round that changed nothing is still a row", () => {
    seed([run({ status: "no_change" }), run({ id: 2, status: "ok" })]);
    render(<SyncRunsTab enabled />);
    expect(rows()).toHaveLength(2);
    expect(screen.getByText(/nothing changed/i)).toBeInTheDocument();
  });

  test("a round that landed no commit says so rather than showing a blank", () => {
    seed([run({ status: "no_change", commit: null })]);
    render(<SyncRunsTab enabled />);
    expect(within(rows()[0]).getAllByRole("cell")[5]).toHaveTextContent("—");
  });

  test("a join is marked, because the same counts mean something else on it", () => {
    seed([run({ join: "new", published: { added: 322, modified: 0, deleted: 0, changes: [] } })]);
    render(<SyncRunsTab enabled />);
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
    render(<SyncRunsTab enabled />);

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
    render(<SyncRunsTab enabled />);

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
    render(<SyncRunsTab enabled />);

    fireEvent.click(screen.getByRole("combobox", { name: /outcome/i }));
    fireEvent.click(screen.getByRole("option", { name: /^failed$/i }));

    expect(rows()).toHaveLength(1);
    expect(screen.queryByText(/nothing changed/i)).not.toBeInTheDocument();
  });

  test("an empty history says so instead of rendering an empty table", () => {
    seed([]);
    render(<SyncRunsTab enabled />);
    expect(screen.getByText(/no round has run yet/i)).toBeInTheDocument();
  });

  test("a daemon that cannot serve the history fails inside this tab", () => {
    // An older daemon has no /sync/runs route. That must not blank Status or
    // Machines, so the error is rendered here rather than thrown upward.
    seed([], { error: new Error("Not Found") });
    render(<SyncRunsTab enabled />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

// `POST /sync/rollback` undoes ONE round — the one that left the newest
// pre-apply snapshot — so the button may appear on exactly one row, and only
// on the row whose round that is. An "Undo" on every row would be a lie: every
// one of them would undo the same, most recent round.
describe("SyncRunsTab — undoing a round", () => {
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
    render(<SyncRunsTab enabled />);

    expect(undoButtons()).toHaveLength(1);
    expect(within(rows()[0]).getByRole("button", { name: /undo this round/i })).toBeInTheDocument();
  });

  test("looks past a round that never reached the snapshot to the one that did", () => {
    // A conflicted round stops at the merge, before the snapshot step: the
    // newest snapshot — and so the round a rollback undoes — is the `ok` one
    // underneath it.
    seed([run({ id: 3, status: "conflict", conflicts: ["knowledge/notes/a.md"] }), run({ id: 2 })]);
    render(<SyncRunsTab enabled />);

    expect(undoButtons()).toHaveLength(1);
    expect(within(rows()[1]).getByRole("button", { name: /undo this round/i })).toBeInTheDocument();
  });

  test("offers no undo when the newest round's status cannot say where it stopped", () => {
    // A `failed` round may have died before the snapshot or after it. Naming
    // the round underneath as the one that gets undone would be a guess, and
    // the wrong guess reverses a round the user did not point at.
    seed([run({ id: 3, status: "failed", error: "network unreachable" }), run({ id: 2 })]);
    render(<SyncRunsTab enabled />);

    expect(undoButtons()).toHaveLength(0);
  });

  test("the confirmation names the round and the documents it would take back", () => {
    seed([run({ id: 3, applied: APPLIED })]);
    render(<SyncRunsTab enabled />);

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
    render(<SyncRunsTab enabled />);

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
    render(<SyncRunsTab enabled />);

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
    render(<SyncRunsTab enabled />);

    fireEvent.click(undoButtons()[0]);
    fireEvent.click(screen.getByRole("button", { name: /^undo round$/i }));

    expect(mutate).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("the undo does not double as the row's expander", () => {
    // The row opens its detail on click; a button inside it that let the click
    // through would open the detail behind the dialog it just raised.
    seed([run({ id: 3, applied: APPLIED })]);
    render(<SyncRunsTab enabled />);

    fireEvent.click(undoButtons()[0]);
    expect(screen.queryByTestId("sync-run-applied")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Folding the quiet rounds, and answering the one that is held.
//
// Both replace a Status tab that carried this as a banner. The fold is why the
// table is readable at all: 14 of 27 rounds on the machine this was built
// against changed nothing.
// ---------------------------------------------------------------------------

describe("SyncRunsTab — quiet rounds", () => {
  const MOVED = {
    added: 1,
    modified: 0,
    deleted: 0,
    changes: [{ path: "a.md", status: "added" as const }],
  };

  test("a stretch of rounds that changed nothing is one row, counted", () => {
    seed([
      run({ id: 5, applied: MOVED }),
      run({ id: 4, status: "no_change" }),
      run({ id: 3, status: "no_change" }),
      run({ id: 2, status: "no_change" }),
    ]);
    render(<SyncRunsTab enabled />);

    // Two rows, not four: the busy one, and the fold under it.
    expect(rows()).toHaveLength(2);
    expect(screen.getByText("×3")).toBeInTheDocument();
  });

  test("the fold reports the stretch it stands in for, so a gap stays visible", () => {
    // The whole reason folding is allowed rather than filtering: a vault that
    // stopped converging must not look like one with nothing to do.
    //
    // Both ends go through `formatDateTime`, which renders in the reader's own
    // zone — asserting the UTC literal would pass only where the test was
    // written.
    const from = "2026-09-13T17:41:43Z";
    const to = "2026-09-13T23:29:47Z";
    // The newest round stands alone (it is the present, not the history), so
    // the fold under it is what reports the stretch.
    seed([
      run({ id: 4, status: "ok" }),
      run({ id: 3, status: "no_change", finished_at: to }),
      run({ id: 2, status: "no_change", started_at: from }),
    ]);
    render(<SyncRunsTab enabled />);

    const row = rows()[1];
    expect(row.textContent).toContain(formatDateTime(from));
    expect(row.textContent).toContain(formatDateTime(to));
  });

  test("opening a fold names the rounds it stands in for", () => {
    seed([
      run({ id: 4, status: "ok" }),
      run({ id: 3, status: "no_change" }),
      run({ id: 2, status: "no_change" }),
    ]);
    render(<SyncRunsTab enabled />);

    fireEvent.click(rows()[1]);
    expect(screen.getByText(/2 rounds between/i)).toBeInTheDocument();
  });

  test("the newest round is never folded away", () => {
    // It is the state the vault is in, and the only row that may carry Undo
    // or an answer to a hold. A summary of its predecessors is no place for
    // a row you can act on.
    seed([
      run({ id: 3, status: "no_change" }),
      run({ id: 2, status: "no_change" }),
      run({ id: 1, status: "no_change" }),
    ]);
    render(<SyncRunsTab enabled />);

    expect(rows()).toHaveLength(2);
  });

  test("a stretch of identical failures folds, and says what they said", () => {
    // The shape this machine was actually left in: an unauthenticated remote
    // is ten rows of the same sentence by morning.
    seed([
      run({ id: 4, status: "failed", error: "git fetch failed: no auth" }),
      run({ id: 3, status: "failed", error: "git fetch failed: no auth" }),
      run({ id: 2, status: "failed", error: "git fetch failed: no auth" }),
    ]);
    render(<SyncRunsTab enabled />);

    expect(rows()).toHaveLength(2);
    fireEvent.click(rows()[1]);
    // Stated once above the times rather than repeated per member — it is the
    // same sentence on every one, which is what let them fold.
    expect(screen.getByText("git fetch failed: no auth")).toBeInTheDocument();
  });

  test("a round that did something is never folded away", () => {
    seed([
      run({ id: 4, status: "no_change" }),
      run({ id: 3, status: "failed", error: "remote unreachable" }),
      run({ id: 2, status: "no_change" }),
    ]);
    render(<SyncRunsTab enabled />);

    // Three rows: the failure keeps its own, and it splits the quiet ones into
    // two stretches that were never consecutive in time.
    expect(rows()).toHaveLength(3);
  });
});

describe("SyncRunsTab — a held round", () => {
  const PENDING = {
    direction: "publish" as const,
    breaches: [{ area: "resources", deleted: 16, total: 45 }],
    paths: ["resources/memory/global.yaml"],
    raised_at: "2026-09-17T00:12:14Z",
  };

  test("the answers sit on the round that is held", () => {
    seed([run({ id: 9, status: "awaiting_confirmation", pending: PENDING })]);
    seedStatus({ last_run: { pending: PENDING, conflicts: [] } });
    render(<SyncRunsTab enabled />);

    expect(screen.getByRole("button", { name: /^confirm$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument();
  });

  test("a round that WAS held offers nothing once the vault is no longer waiting", () => {
    // Exactly the state this machine was left in: two rows still reading
    // `awaiting_confirmation`, the situation already answered. A button there
    // would act on a pending state that no longer exists.
    seed([
      run({ id: 9, status: "awaiting_confirmation", pending: PENDING }),
      run({ id: 8, status: "awaiting_confirmation", pending: PENDING }),
    ]);
    seedStatus({ last_run: { pending: null, conflicts: [] } });
    render(<SyncRunsTab enabled />);

    expect(screen.queryByRole("button", { name: /^confirm$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^reject$/i })).toBeNull();
  });

  test("a round that WAS held stops SAYING it is waiting for you", () => {
    // The buttons were already gated; the words were not. Four rows from last
    // Tuesday each read "paused — waiting for you" about an answer that was
    // given days ago, which is the page telling a reader to do something
    // there is nothing to do about.
    seed([
      run({ id: 9, status: "awaiting_confirmation", pending: PENDING }),
      run({ id: 8, status: "ok" }),
    ]);
    seedStatus({ last_run: { pending: null, conflicts: [] } });
    render(<SyncRunsTab enabled />);

    expect(screen.getByText("Paused")).toBeInTheDocument();
    expect(screen.queryByText(/waiting for you/i)).toBeNull();
  });

  test("the round that IS held still says so", () => {
    seed([run({ id: 9, status: "awaiting_confirmation", pending: PENDING })]);
    seedStatus({ last_run: { pending: PENDING, conflicts: [] } });
    render(<SyncRunsTab enabled />);

    expect(screen.getByText(/waiting for you/i)).toBeInTheDocument();
  });

  test("only the newest held round carries them, never an older one too", () => {
    seed([
      run({ id: 9, status: "awaiting_confirmation", pending: PENDING }),
      run({ id: 8, status: "awaiting_confirmation", pending: PENDING }),
    ]);
    seedStatus({ last_run: { pending: PENDING, conflicts: [] } });
    render(<SyncRunsTab enabled />);

    expect(screen.getAllByRole("button", { name: /^confirm$/i })).toHaveLength(1);
  });

  test("a conflict stays a banner — its paths need a working tree the table has no column for", () => {
    seed([run({ id: 9, status: "conflict", conflicts: ["knowledge/notes/plan.md"] })]);
    seedStatus({
      last_run: { pending: null, conflicts: ["knowledge/notes/plan.md"] },
      remote: { worktree_path: "/home/me/.coffer/sync" },
    });
    render(<SyncRunsTab enabled />);

    const banner = screen.getByTestId("sync-conflict-banner");
    expect(banner).toHaveTextContent("knowledge/notes/plan.md");
    expect(banner).toHaveTextContent("/home/me/.coffer/sync");
  });
});
