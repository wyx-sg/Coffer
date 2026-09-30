// frontend/src/pages/sync/SyncRunsTab.test.tsx
//
// The Runs table: every round, not just the newest; pulled and pushed kept
// apart; the commits a round moved between; repeated outcomes folded into one
// counted row; and rollback on the rounds that can be rolled back, asking
// first with the plan the daemon states.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { SyncRound } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { acceptance } from "@/test/acceptance";
import { SyncRunsTab } from "./SyncRunsTab";
import { idleMutation, makeRound } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncRuns: vi.fn(),
  useRollbackPlan: vi.fn(),
  useRollbackRound: vi.fn(),
}));
// The cards above the table have tests of their own.
vi.mock("./SyncStatusSection", () => ({ SyncStatusSection: () => null }));

const { useSyncRuns, useRollbackPlan, useRollbackRound } = await import("@/lib/hooks/useSync");

const APPLIED = [
  { path: "knowledge/notes/a.md", status: "added" as const },
  { path: "resources/channel/seatalk.yaml", status: "modified" as const },
];

function seed(rounds: SyncRound[], state: { isLoading?: boolean; error?: unknown } = {}) {
  vi.mocked(useSyncRuns).mockReturnValue({
    data: state.isLoading || state.error ? undefined : { rounds, total: rounds.length },
    isLoading: Boolean(state.isLoading),
    error: state.error ?? null,
  } as unknown as ReturnType<typeof useSyncRuns>);
}

function seedRollback(mutate = vi.fn()) {
  vi.mocked(useRollbackRound).mockReturnValue(
    idleMutation({ mutate }) as unknown as ReturnType<typeof useRollbackRound>,
  );
  vi.mocked(useRollbackPlan).mockReturnValue({
    data: {
      snapshot: "sync/pre-round/3",
      snapshot_commit: "abc123",
      snapshot_time: "2026-09-13T09:00:00Z",
      reverses: [
        { path: "knowledge/notes/a.md", status: "removed" },
        { path: "resources/channel/seatalk.yaml", status: "modified" },
      ],
      kept: ["knowledge/notes/edited-since.md"],
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useRollbackPlan>);
  return mutate;
}

const rows = () => screen.getAllByRole("row").slice(1);
const rollbackButtons = () => screen.queryAllByRole("button", { name: /^roll back$/i });

beforeEach(() => void seedRollback());
afterEach(() => vi.clearAllMocks());

describe("SyncRunsTab", () => {
  test("lists every round, with pulled and pushed apart and the commits it moved", () => {
    seed([
      makeRound({
        id: 3,
        status: "pulled_and_pushed",
        pulled_files: 4,
        pushed_files: 322,
        from_commit: "aaaaaaa111",
        to_commit: "bbbbbbb222",
      }),
      makeRound({ id: 2, status: "pushed" }),
      makeRound({ id: 1, status: "pulled" }),
    ]);
    render(<SyncRunsTab enabled />);

    expect(rows()).toHaveLength(3);
    const cells = within(rows()[0]).getAllByRole("cell");
    // [expander, when, status, pulled, pushed, commits, actions]
    expect(cells[3]).toHaveTextContent("4");
    expect(cells[4]).toHaveTextContent("322");
    expect(cells[5]).toHaveTextContent("aaaaaaa..bbbbbbb");
  });

  test("a round that moved the vault nowhere shows a dash, not a blank", () => {
    seed([makeRound({ status: "nothing_to_do" })]);
    render(<SyncRunsTab enabled />);
    expect(within(rows()[0]).getAllByRole("cell")[5]).toHaveTextContent("—");
  });

  test("the status filter narrows to the rounds that went wrong", () => {
    seed([
      makeRound({ id: 2, status: "pulled" }),
      makeRound({ id: 1, status: "auth_failed", detail: "HTTP 403" }),
    ]);
    render(<SyncRunsTab enabled />);
    fireEvent.click(screen.getByRole("combobox", { name: /status/i }));
    fireEvent.click(screen.getByRole("option", { name: /sign-in refused/i }));
    expect(rows()).toHaveLength(1);
  });

  test("an empty history says so", () => {
    seed([]);
    render(<SyncRunsTab enabled />);
    expect(screen.getByText(/no round has run yet/i)).toBeInTheDocument();
  });

  test("a history that cannot be read fails inside this tab", () => {
    seed([], { error: new Error("Not Found") });
    render(<SyncRunsTab enabled />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("Not Found")).toBeInTheDocument();
  });

  acceptance("vault-sync", "consecutive quiet rounds fold into one counted row", () => {
    const from = "2026-09-13T17:41:43Z";
    const to = "2026-09-13T23:29:47Z";
    seed([
      makeRound({ id: 5, status: "pulled", applied: APPLIED }),
      makeRound({ id: 4, finished_at: to }),
      makeRound({ id: 3 }),
      makeRound({ id: 2, started_at: from }),
    ]);
    render(<SyncRunsTab enabled />);

    expect(rows()).toHaveLength(2);
    const fold = rows()[1];
    expect(within(fold).getByText("×3")).toBeInTheDocument();
    expect(fold.textContent).toContain(formatDateTime(from));
    expect(fold.textContent).toContain(formatDateTime(to));
    fireEvent.click(fold);
    expect(screen.getByText(/3 rounds between/i)).toBeInTheDocument();
  });
});

describe("SyncRunsTab — rolling a round back", () => {
  test("only rounds that snapshotted and changed files here offer it", () => {
    seed([
      makeRound({ id: 3, status: "pulled", snapshot: "sync/pre-round/3", applied: APPLIED }),
      makeRound({ id: 2, status: "pushed", snapshot: "sync/pre-round/2", pushed: APPLIED }),
      makeRound({ id: 1, status: "pulled", snapshot: null, applied: APPLIED }),
    ]);
    render(<SyncRunsTab enabled />);
    expect(rollbackButtons()).toHaveLength(1);
    expect(within(rows()[0]).getByRole("button", { name: /^roll back$/i })).toBeInTheDocument();
  });

  acceptance("vault-sync", "a round can be rolled back", () => {
    const mutate = seedRollback(
      vi.fn((_id: number, opts: { onSuccess: () => void }) => opts.onSuccess()),
    );
    seed([makeRound({ id: 3, status: "pulled", snapshot: "sync/pre-round/3", applied: APPLIED })]);
    render(<SyncRunsTab enabled />);

    fireEvent.click(rollbackButtons()[0]);
    const dialog = within(screen.getByRole("dialog"));
    // The plan, stated before anything happens: which snapshot, what comes
    // back, and that later edits are kept.
    expect(dialog.getByText(/sync\/pre-round\/3/)).toBeInTheDocument();
    expect(dialog.getByTestId("sync-rollback-paths")).toHaveTextContent("− knowledge/notes/a.md");
    expect(dialog.getByTestId("sync-rollback-paths")).toHaveTextContent(
      "~ resources/channel/seatalk.yaml",
    );
    expect(dialog.getByText(/edits you made after are kept/i)).toBeInTheDocument();
    expect(dialog.getByTestId("sync-rollback-kept")).toHaveTextContent("edited-since.md");
    expect(mutate).not.toHaveBeenCalled();

    fireEvent.click(dialog.getByRole("button", { name: /^roll back round$/i }));
    expect(mutate).toHaveBeenCalledWith(3, expect.anything());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("a refused rollback keeps the dialog open with its reason", () => {
    seedRollback();
    vi.mocked(useRollbackRound).mockReturnValue(
      idleMutation({ error: new Error("snapshot is gone") }) as unknown as ReturnType<
        typeof useRollbackRound
      >,
    );
    seed([makeRound({ id: 3, status: "pulled", snapshot: "s", applied: APPLIED })]);
    render(<SyncRunsTab enabled />);
    fireEvent.click(rollbackButtons()[0]);
    // The error is there from the start, so the confirm already reads "Try again".
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: /^(roll back round|try again)$/i,
      }),
    );
    expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent(
      /snapshot is gone/,
    );
  });
});
