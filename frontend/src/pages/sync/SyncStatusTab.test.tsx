// frontend/src/pages/sync/SyncStatusTab.test.tsx
//
// Sync › Status: the one state in a sentence (and a card when it asks for
// something), the areas line, what waits to push, the stopped round's
// list and the join's choices when there is one, and every round — folded
// where rounds repeated, each opening its detail, and rolled back only after
// the dialog states the plan.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { SyncRound, SyncStatus } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncStatusTab } from "./SyncStatusTab";
import { syncState } from "./syncPageState";
import { idleMutation, makeMachine, makeRound, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncRuns: vi.fn(),
  useRollbackPlan: vi.fn(),
  useRollbackRound: vi.fn(),
}));
vi.mock("@/lib/hooks/useSyncStop", () => ({
  useSyncStop: vi.fn(),
  useHandoffRequest: vi.fn(() => vi.fn()),
}));
// Ignore reads the attention list; here no item is ignored and none can be.
const mockedIgnore = {
  isIgnored: vi.fn<(reason: string) => boolean>(() => false),
  ignorer: vi.fn<(reason: string) => (() => void) | undefined>(() => undefined),
};
vi.mock("./useSyncIgnore", async (orig) => ({
  ...(await orig<typeof import("./useSyncIgnore")>()),
  useSyncIgnore: () => mockedIgnore,
}));
vi.mock("@/components/secret/ScanSecretsDialog", () => ({ ScanSecretsDialog: () => null }));
vi.mock("./SyncMoveVaultDialog", () => ({
  SyncMoveVaultDialog: ({ open }: { open: boolean }) => (open ? <div>move dialog</div> : null),
}));
vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn() }));
vi.mock("@/lib/api/fs", () => ({ fsApi: { reveal: vi.fn(() => Promise.resolve()) } }));
// B's and C's cards have tests of their own; here they only need to be placed.
vi.mock("./SyncStoppedCard", () => ({ SyncStoppedCard: () => <div>stopped card</div> }));
vi.mock("./SyncJoinChoices", () => ({ SyncJoinChoices: () => <div>join choices</div> }));
vi.mock("@/components/handoff/AgentHandoff", () => ({
  AgentHandoff: ({ prompt }: { prompt: string }) => <div data-testid="handoff">{prompt}</div>,
}));

const { useSyncRuns, useRollbackPlan, useRollbackRound } = await import("@/lib/hooks/useSync");
const { useSyncStop } = await import("@/lib/hooks/useSyncStop");
const { useMachines } = await import("@/lib/hooks/useMachines");
const { fsApi } = await import("@/lib/api/fs");

// Local noon, so "Today" and "Yesterday" are stable whatever the machine's zone.
const NOW = new Date(2026, 8, 29, 15, 0, 0);
const at = (h: number, m: number, day = 29) => new Date(2026, 8, day, h, m, 0).toISOString();

const APPLIED = [
  { path: "knowledge/notes/a.md", status: "added" as const },
  { path: "resources/channel/seatalk.yaml", status: "modified" as const },
];

function seedRuns(
  rounds: SyncRound[],
  state: {
    isLoading?: boolean;
    error?: unknown;
    total?: number;
    hasMore?: boolean;
    loadMore?: () => void;
    refetch?: () => void;
  } = {},
) {
  vi.mocked(useSyncRuns).mockReturnValue({
    items: rounds,
    total: state.total ?? rounds.length,
    totalIsFloor: false,
    hasMore: state.hasMore ?? false,
    loadMore: state.loadMore ?? vi.fn(),
    isLoading: Boolean(state.isLoading),
    isLoadingMore: false,
    isRefreshing: false,
    error: state.error ?? null,
    refetch: state.refetch ?? vi.fn(),
  } as ReturnType<typeof useSyncRuns>);
}

function seedRollback(mutate = vi.fn(), error: unknown = null) {
  vi.mocked(useRollbackRound).mockReturnValue(
    idleMutation({ mutate, error }) as unknown as ReturnType<typeof useRollbackRound>,
  );
  vi.mocked(useRollbackPlan).mockReturnValue({
    data: {
      snapshot: "snap-0929-1432",
      snapshot_commit: "abc123",
      snapshot_time: at(14, 32),
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

function renderTab(status: SyncStatus, { pending = false, onRecheck = vi.fn() } = {}) {
  return render(
    <TooltipProvider>
      <MemoryRouter>
        <SyncStatusTab
          status={status}
          state={syncState(status, pending)}
          startedAt={pending ? at(14, 32) : null}
          onRecheck={onRecheck}
          rechecking={false}
        />
      </MemoryRouter>
    </TooltipProvider>,
  );
}

const banner = () => screen.getAllByTestId(/^sync-(banner|problem)$/)[0];
const tableRows = () => screen.getAllByRole("row").slice(1);
const rollbackButtons = () => screen.queryAllByRole("button", { name: /^roll back$/i });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  seedRuns([]);
  seedRollback();
  vi.mocked(useSyncStop).mockReturnValue({ data: undefined } as unknown as ReturnType<
    typeof useSyncStop
  >);
  vi.mocked(useMachines).mockReturnValue({
    data: {
      machines: [
        makeMachine(),
        makeMachine({ machine_id: "m2", name: "Mac mini", is_self: false }),
      ],
    },
  } as unknown as ReturnType<typeof useMachines>);
});
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("SyncStatusTab — the state line", () => {
  test("in sync: the last round, the next one and how many machines, above the areas line", () => {
    renderTab(
      makeStatus({
        last_round: makeRound({
          status: "pulled_and_pushed",
          finished_at: at(14, 48),
          pulled_files: 2,
          pushed_files: 1,
        }),
        next_round_at: at(15, 20),
        machines: 2,
        areas: {
          knowledge_documents: 142,
          skills: 38,
          resources: 24,
          secrets: 3,
          secrets_synced: false,
        },
      }),
    );
    expect(banner()).toHaveTextContent("This Mac matches the remote");
    expect(banner()).toHaveTextContent(
      "Last round 14:48, 12 minutes ago: pulled 2, pushed 1 · next round at 15:20 · 2 machines",
    );
    // One grey line under the state, not four tiles.
    expect(screen.getByTestId("sync-areas")).toHaveTextContent(
      "Syncs 142 knowledge documents · 38 skills · 24 MCP server and tool definitions · secrets not synced",
    );
  });

  test("changes to push: the sentence names the one other Mac, and every waiting file is listed", () => {
    renderTab(
      makeStatus({
        next_round_at: at(15, 20),
        waiting: [
          {
            version: "v1",
            time: at(14, 28),
            writer: "user",
            summary: "",
            changes: [{ path: "knowledge/team-runbooks/on-call.md", status: "modified" }],
          },
          {
            version: "v2",
            time: at(14, 30),
            writer: "daemon",
            summary: "",
            changes: [{ path: "skills/pdf-tools/SKILL.md", status: "added" }],
          },
        ],
      }),
    );
    expect(banner()).toHaveTextContent("2 changes on this Mac are waiting to push");
    expect(banner()).toHaveTextContent(
      "They go out in the next round at 15:20, after this Mac pulls whatever Mac mini pushed.",
    );
    const lines = within(screen.getByTestId("sync-waiting")).getAllByRole("listitem");
    expect(lines[0]).toHaveTextContent("~knowledge/team-runbooks/on-call.md");
    expect(lines[0]).toHaveTextContent("You · 14:28");
    expect(lines[1]).toHaveTextContent("+skills/pdf-tools/SKILL.md");
    expect(lines[1]).toHaveTextContent("Coffer · 14:30");
  });

  test("changes pulled: from whom, and that there was nothing to push", () => {
    renderTab(
      makeStatus({
        last_round: makeRound({
          status: "pulled",
          finished_at: at(14, 32),
          pulled_files: 3,
          pulled: [{ version: "c9e1b07aaa", machine: "Mac mini", files: 3, time: at(14, 5) }],
        }),
        next_round_at: at(15, 32),
      }),
    );
    expect(banner()).toHaveTextContent("Pulled 3 changes from Mac mini");
    expect(banner()).toHaveTextContent("Round at 14:32 · nothing to push · next round at 15:32");
  });

  test("syncing: when the round started, and no step list the daemon cannot report", () => {
    renderTab(makeStatus({ running_since: at(14, 32) }));
    expect(banner()).toHaveTextContent("Round started at 14:32");
    expect(banner()).toHaveTextContent("Pulling first, then applying, then pushing.");
  });

  test("rolled back: names the round it undid", () => {
    const undone = makeRound({
      id: 7,
      status: "pulled",
      snapshot: "snap-0929-1432",
      finished_at: at(14, 32),
      applied: APPLIED,
    });
    const rollback = makeRound({
      id: 8,
      status: "rolled_back",
      snapshot: "snap-0929-1432",
      trigger: "manual",
      finished_at: at(14, 41),
      applied: APPLIED,
    });
    seedRuns([rollback, undone]);
    renderTab(makeStatus({ last_round: rollback, next_round_at: at(15, 32) }));
    expect(banner()).toHaveTextContent("Rolled back to before the 14:32 round");
    expect(banner()).toHaveTextContent(
      "The rollback goes out in the next round at 15:32, so Mac mini gets it too.",
    );
    // The rollback's own row names it too, with no Roll back and no Commits column.
    expect(tableRows()[0]).toHaveTextContent("Rolled back the 14:32 round · by you");
    expect(screen.queryByRole("columnheader", { name: "Commits" })).toBeNull();
  });

  test("a paused remote says so and asks for nothing", () => {
    const status = makeStatus();
    renderTab({ ...status, remote: { ...status.remote!, enabled: false } });
    expect(banner()).toHaveTextContent("Sync is paused on this Mac");
  });
});

describe("SyncStatusTab — a stopped round", () => {
  test("conflicts: the card names the other Mac, links to Resolve conflicts, and B's list sits under the state", () => {
    vi.mocked(useSyncStop).mockReturnValue({
      data: {
        stopped: true,
        round: { kind: "conflicts", files: [{ path: "a.md", theirs_machine: "Mac mini" }] },
      },
    } as unknown as ReturnType<typeof useSyncStop>);
    renderTab(makeStatus({ conflicts: 2 }));
    expect(banner()).toHaveTextContent("This round stopped on 2 conflicts");
    expect(banner()).toHaveTextContent("This Mac and Mac mini changed the same lines.");
    expect(within(banner()).getByRole("link", { name: "Resolve conflicts" })).toHaveAttribute(
      "href",
      "/sync/conflicts",
    );
    const card = screen.getByText("stopped card");
    // Between the banner and the Rounds table; a card asks something, so no areas line.
    expect(screen.queryByTestId("sync-areas")).toBeNull();
    expect(banner().compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      card.compareDocumentPosition(screen.getByRole("table")) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  test("held deletions: who deleted how many, and Review deletions", () => {
    vi.mocked(useSyncStop).mockReturnValue({
      data: {
        stopped: true,
        round: { kind: "hold", files: [], hold: { direction: "incoming", machines: ["Mac mini"] } },
      },
    } as unknown as ReturnType<typeof useSyncStop>);
    renderTab(makeStatus({ held: 14 }));
    expect(banner()).toHaveTextContent("Mac mini deleted 14 files, more than one round may delete");
    expect(within(banner()).getByRole("link", { name: "Review deletions" })).toHaveAttribute(
      "href",
      "/sync/deletions",
    );
    expect(screen.getByText("stopped card")).toBeInTheDocument();
  });

  test("a join's differing files are shown when the status says there are some", () => {
    renderTab(makeStatus({ join_choices: 2 }));
    expect(screen.getByText("join choices")).toBeInTheDocument();
    expect(screen.queryByText("stopped card")).not.toBeInTheDocument();
  });
});

describe("SyncStatusTab — problems", () => {
  const problem = (over: Partial<NonNullable<SyncStatus["problem"]>>) => ({
    kind: "failed" as const,
    message: "",
    secret_ref: null,
    since: null,
    handoff: null,
    plaintext: [],
    ...over,
  });

  test("push rejected: git's words in full and the hand-off, no Retry in the card", () => {
    renderTab(
      makeStatus({
        last_round: makeRound({ status: "push_failed", pulled_files: 3 }),
        waiting: [
          {
            version: "v1",
            time: at(14, 20),
            writer: "user",
            summary: "",
            changes: [
              { path: "a.md", status: "modified" },
              { path: "b.md", status: "added" },
            ],
          },
        ],
        problem: problem({
          kind: "push_failed",
          message: "! [remote rejected] main -> main (protected branch hook declined)",
          handoff: { prompt: "fix the push" },
        }),
      }),
    );
    const card = screen.getByTestId("sync-problem");
    expect(card).toHaveTextContent("Pulled and applied, but the push was rejected");
    expect(card).toHaveTextContent(
      "This Mac took 3 changes from the remote. Its own 2 changes did not go out",
    );
    expect(card).toHaveTextContent("protected branch hook declined");
    expect(within(card).queryByRole("button", { name: "Retry" })).toBeNull();
    expect(within(card).getByTestId("handoff")).toHaveTextContent("fix the push");
    // Nothing is waiting to be listed while the card explains the push.
    expect(screen.queryByTestId("sync-waiting")).not.toBeInTheDocument();
  });

  test("unreachable: a plain sentence with git's message folded away", () => {
    seedRuns([
      makeRound({ id: 2, status: "unreachable", finished_at: at(14, 50) }),
      makeRound({ id: 1, status: "pulled_and_pushed", finished_at: at(14, 20) }),
    ]);
    renderTab(
      makeStatus({
        problem: problem({
          kind: "unreachable",
          message: "ssh: connect to host github.com port 22: Network is unreachable",
          handoff: { prompt: "check the network" },
        }),
        remote: { ...makeStatus().remote!, url: "git@github.com:yuxing/coffer-vault.git" },
      }),
    );
    const card = screen.getByTestId("sync-problem");
    expect(card).toHaveTextContent("github.com can’t be reached");
    expect(card).toHaveTextContent("No round has finished since 14:20.");
    const details = card.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    expect(within(card).getByText("Show git's message")).toBeInTheDocument();
    expect(within(card).getByTestId("handoff")).toHaveTextContent("check the network");
  });

  test("sign-in failed: names the secret, Choose secret and Open in Secrets, no hand-off", () => {
    renderTab(
      makeStatus({
        problem: problem({
          kind: "auth_failed",
          secret_ref: "github-deploy-key",
          message: "Permission denied (publickey).",
        }),
      }),
    );
    const card = screen.getByTestId("sync-problem");
    expect(card).toHaveTextContent("The remote refused the secret");
    expect(card).toHaveTextContent("github-deploy-key was rejected by git.example.com.");
    expect(within(card).getByRole("link", { name: "Choose secret" })).toHaveAttribute(
      "href",
      "/sync?tab=remote&focus=secret",
    );
    expect(within(card).getByRole("link", { name: "Open in Secrets" })).toHaveAttribute(
      "href",
      "/secrets",
    );
    expect(within(card).queryByTestId("handoff")).toBeNull();
  });

  test("cloud folder: the vault's path and the tool, Move the vault… and Reveal in Finder", () => {
    renderTab(
      makeStatus({
        problem: problem({ kind: "cloud_folder" }),
        synchroniser: "iCloud Drive",
        vault_path: "/Users/me/.coffer/vault",
        vault_real_path: "/Users/me/Library/Mobile Documents/Coffer",
      }),
    );
    const card = screen.getByTestId("sync-problem");
    expect(card).toHaveTextContent("Your vault is inside iCloud Drive");
    expect(card).toHaveTextContent(
      "/Users/me/Library/Mobile Documents/Coffer is also moved around",
    );
    fireEvent.click(within(card).getByRole("button", { name: "Move the vault…" }));
    expect(screen.getByText("move dialog")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Reveal in Finder" }));
    expect(fsApi.reveal).toHaveBeenCalledWith("/Users/me/Library/Mobile Documents/Coffer");
  });

  test("git missing: a sentence, the backend's hand-off and Check again", () => {
    const onRecheck = vi.fn();
    renderTab(
      makeStatus({ problem: problem({ kind: "git_missing", handoff: { prompt: "install git" } }) }),
      { onRecheck },
    );
    const card = screen.getByTestId("sync-problem");
    expect(card).toHaveTextContent("Git isn’t installed on this Mac");
    expect(within(card).getByTestId("handoff")).toHaveTextContent("install git");
    fireEvent.click(within(card).getByRole("button", { name: "Check again" }));
    expect(onRecheck).toHaveBeenCalled();
  });

  test("every card's × is Ignore: it asks the daemon to ignore that attention item", () => {
    const ignore = vi.fn();
    mockedIgnore.ignorer.mockImplementation((reason: string) =>
      reason === "sync_unreachable" ? ignore : undefined,
    );
    renderTab(makeStatus({ problem: problem({ kind: "unreachable", message: "x" }) }));
    fireEvent.click(
      within(screen.getByTestId("sync-problem")).getByRole("button", { name: "Ignore" }),
    );
    expect(ignore).toHaveBeenCalled();
  });

  test("an ignored problem shows no card", () => {
    mockedIgnore.isIgnored.mockImplementation((reason: string) => reason === "sync_unreachable");
    renderTab(makeStatus({ problem: problem({ kind: "unreachable", message: "x" }) }));
    expect(screen.queryByTestId("sync-problem")).toBeNull();
  });
});

describe("SyncStatusTab — Rounds", () => {
  test("each round's word and clause, pulled and pushed apart, and the commits it moved", () => {
    seedRuns([
      makeRound({
        id: 3,
        status: "pulled_and_pushed",
        finished_at: at(14, 20),
        pulled_files: 2,
        pushed_files: 1,
        with_machines: ["Mac mini"],
        from_commit: "77c5e2baaaa",
        to_commit: "a81d03ebbbb",
      }),
      makeRound({ id: 2, status: "auth_failed", finished_at: at(14, 10) }),
      makeRound({ id: 1, status: "pulled", finished_at: at(22, 20, 28), pulled_files: 4 }),
    ]);
    renderTab(makeStatus());
    // Only the section title: no description line, no help tip, no Commits column.
    expect(screen.getByRole("heading", { name: "Rounds" })).toBeInTheDocument();
    expect(
      within(screen.getByTestId("sync-rounds")).queryByRole("button", { name: "More info" }),
    ).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Commits" })).toBeNull();
    // The boards draw no search box and no status filter.
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    const [first, second, third] = tableRows();
    expect(first).toHaveTextContent("Today 14:20");
    expect(first).toHaveTextContent("Pulled and pushed · with Mac mini");
    expect(within(first).getAllByRole("cell")[2]).toHaveTextContent("2");
    expect(within(first).getAllByRole("cell")[3]).toHaveTextContent("1");
    expect(second).toHaveTextContent("Sign-in failed · nothing pulled or pushed");
    expect(within(second).getAllByRole("cell")[2]).toHaveTextContent("—");
    expect(third).toHaveTextContent("Yesterday 22:20");
  });

  test("a long history shows how many of its rounds are loaded and loads the next page on request", () => {
    const loadMore = vi.fn();
    seedRuns([makeRound({ id: 9, status: "pulled", applied: APPLIED })], {
      total: 130,
      hasMore: true,
      loadMore,
    });
    renderTab(makeStatus());
    expect(screen.getByText("Loaded 1 of 130 rounds")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  test("with every round loaded the footer still counts rounds", () => {
    seedRuns([makeRound({ id: 9, status: "pulled", applied: APPLIED })], { total: 1 });
    renderTab(makeStatus());
    expect(screen.getByText("Loaded 1 of 1 rounds")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  test("an empty history says so; a failing one fails inside the tab", () => {
    renderTab(makeStatus());
    expect(screen.getByText("No round has run yet.")).toBeInTheDocument();
    seedRuns([], { error: new Error("Not Found") });
    renderTab(makeStatus());
    expect(screen.getByText("Not Found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  acceptance("vault-sync", "consecutive quiet rounds fold into one counted row", () => {
    seedRuns([
      makeRound({ id: 5, status: "pulled", applied: APPLIED, finished_at: at(14, 20) }),
      makeRound({ id: 4, started_at: at(13, 20), finished_at: at(13, 20) }),
      makeRound({ id: 3, started_at: at(11, 20), finished_at: at(11, 20) }),
      makeRound({ id: 2, started_at: at(8, 20), finished_at: at(8, 20) }),
    ]);
    renderTab(makeStatus());

    expect(tableRows()).toHaveLength(2);
    const fold = tableRows()[1];
    // The span and the count, in one row.
    expect(fold).toHaveTextContent("Today 08:20 – 13:20");
    expect(fold).toHaveTextContent("Nothing to do ×3");
    // Every round in it is still reachable from that row.
    fireEvent.click(fold);
    const drawer = within(screen.getByRole("dialog"));
    expect(drawer.getByText("Today 13:20")).toBeInTheDocument();
    expect(drawer.getByText("Today 11:20")).toBeInTheDocument();
    fireEvent.click(drawer.getByText("Today 08:20"));
    expect(
      within(screen.getByRole("dialog")).getByText("Round at 08:20 today"),
    ).toBeInTheDocument();
  });

  test("a row opens its round's drawer", () => {
    seedRuns([
      makeRound({
        id: 3,
        status: "pulled",
        snapshot: "snap-0929-1432",
        applied: APPLIED,
        finished_at: at(14, 32),
      }),
    ]);
    renderTab(makeStatus());
    fireEvent.click(tableRows()[0]);
    const drawer = within(screen.getByRole("dialog"));
    expect(drawer.getByText("Round at 14:32 today")).toBeInTheDocument();
    expect(drawer.getByTestId("sync-run-applied")).toHaveTextContent("+knowledge/notes/a.md");
  });
});

describe("SyncStatusTab — rolling a round back", () => {
  test("the plan list stops at five and scrolls inside the dialog once expanded", () => {
    seedRollback();
    vi.mocked(useRollbackPlan).mockReturnValue({
      data: {
        snapshot: "snap-1",
        snapshot_commit: "abc",
        snapshot_time: at(14, 32),
        reverses: Array.from({ length: 23 }, (_, i) => ({
          path: `knowledge/n${i}.md`,
          status: "removed" as const,
        })),
        kept: [],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useRollbackPlan>);
    seedRuns([makeRound({ id: 3, status: "pulled", snapshot: "s", applied: APPLIED })]);
    renderTab(makeStatus());
    fireEvent.click(tableRows()[0]);
    fireEvent.click(screen.getByRole("button", { name: "Roll back to before this round" }));
    const dialog = within(screen.getByRole("dialog"));
    const paths = within(dialog.getByTestId("sync-rollback-paths"));
    expect(paths.getAllByRole("listitem")).toHaveLength(5);
    fireEvent.click(paths.getByRole("button", { name: "Show all" }));
    expect(paths.getAllByRole("listitem")).toHaveLength(23);
    expect(paths.getAllByRole("list")[0].className).toContain("overflow-y-auto");
  });

  test("a row has no Roll back; only the drawer of a round that snapshotted and changed files has one", () => {
    seedRuns([
      makeRound({ id: 3, status: "pulled", snapshot: "s3", applied: APPLIED }),
      makeRound({ id: 2, status: "pushed", snapshot: "s2", pushed: APPLIED }),
    ]);
    renderTab(makeStatus());
    expect(rollbackButtons()).toHaveLength(0);
    fireEvent.click(tableRows()[0]);
    expect(
      screen.getByRole("button", { name: "Roll back to before this round" }),
    ).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    fireEvent.click(tableRows()[1]);
    expect(screen.queryByRole("button", { name: "Roll back to before this round" })).toBeNull();
  });

  acceptance("vault-sync", "a round can be rolled back", () => {
    const mutate = seedRollback(
      vi.fn((_id: number, opts: { onSuccess: () => void }) => opts.onSuccess()),
    );
    seedRuns([
      makeRound({
        id: 3,
        status: "pulled",
        snapshot: "snap-0929-1432",
        applied: APPLIED,
        pulled_files: 3,
        finished_at: at(14, 32),
      }),
    ]);
    renderTab(makeStatus());

    fireEvent.click(tableRows()[0]);
    fireEvent.click(screen.getByRole("button", { name: "Roll back to before this round" }));
    const dialog = within(screen.getByRole("dialog"));
    // The plan, stated before anything happens: which snapshot, what comes
    // back, that the other Macs follow and that later edits are kept.
    expect(dialog.getByText("Roll back to before the 14:32 round?")).toBeInTheDocument();
    expect(dialog.getByText(/snap-0929-1432/)).toBeInTheDocument();
    expect(dialog.getByTestId("sync-rollback-paths")).toHaveTextContent("−knowledge/notes/a.md");
    expect(dialog.getByTestId("sync-rollback-paths")).toHaveTextContent("added");
    expect(dialog.getByTestId("sync-rollback-paths")).toHaveTextContent(
      "~resources/channel/seatalk.yaml",
    );
    // "Other Macs follow" is one line, with the kept edits in it.
    expect(
      dialog.getByText(/the other Macs get it too.*edits you made after 14:32 are kept/i),
    ).toBeInTheDocument();
    expect(dialog.getByTestId("sync-rollback-kept")).toHaveTextContent("edited-since.md");
    expect(mutate).not.toHaveBeenCalled();

    fireEvent.click(dialog.getByRole("button", { name: /^roll back$/i }));
    expect(mutate).toHaveBeenCalledWith(3, expect.anything());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("the drawer's footer rolls the round back through the same dialog", () => {
    seedRuns([
      makeRound({
        id: 3,
        status: "pulled",
        snapshot: "s",
        applied: APPLIED,
        finished_at: at(14, 32),
      }),
    ]);
    renderTab(makeStatus());
    fireEvent.click(tableRows()[0]);
    fireEvent.click(screen.getByRole("button", { name: "Roll back to before this round" }));
    expect(screen.getByText("Roll back to before the 14:32 round?")).toBeInTheDocument();
  });

  test("a refused rollback keeps the dialog open with its reason", () => {
    seedRollback(vi.fn(), new Error("snapshot is gone"));
    seedRuns([makeRound({ id: 3, status: "pulled", snapshot: "s", applied: APPLIED })]);
    renderTab(makeStatus());
    fireEvent.click(tableRows()[0]);
    fireEvent.click(screen.getByRole("button", { name: "Roll back to before this round" }));
    const dialog = within(screen.getByRole("dialog"));
    fireEvent.click(dialog.getByRole("button", { name: /^(roll back|retry)$/i }));
    expect(dialog.getByRole("alert")).toHaveTextContent(/snapshot is gone/);
  });
});
