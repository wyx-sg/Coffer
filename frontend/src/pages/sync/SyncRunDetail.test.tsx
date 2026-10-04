// frontend/src/pages/sync/SyncRunDetail.test.tsx
//
// A round's drawer (6.4.04) names what its row could only count, in the four
// steps every round takes: the snapshot, the commits pulled and from whom, the
// files applied here, the files pushed — and its footer rolls it back or opens
// Activity. A long list of applied files stops at five until Show all.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { SyncRound } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncRunDetail } from "./SyncRunDetail";
import { makeRound } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ useRoundFileDiff: vi.fn() }));
const { useRoundFileDiff } = await import("@/lib/hooks/useSync");
const diffResult = (data: unknown) =>
  vi
    .mocked(useRoundFileDiff)
    .mockReturnValue({ data, isLoading: false, error: null } as unknown as ReturnType<
      typeof useRoundFileDiff
    >);

function open(run: SyncRound, onRollback = vi.fn()) {
  const row = { kind: "run" as const, id: String(run.id), run };
  render(
    <MemoryRouter>
      <SyncRunDetail
        row={row}
        rows={[row]}
        onClose={vi.fn()}
        onOpen={vi.fn()}
        onRollback={onRollback}
      />
    </MemoryRouter>,
  );
  return within(screen.getByRole("dialog"));
}

describe("SyncRunDetail", () => {
  beforeEach(() => diffResult(undefined));

  test("names the snapshot, the pulled commits and the files moved each way", () => {
    const drawer = open(
      makeRound({
        status: "pulled_and_pushed",
        snapshot: "snap-0929-1432",
        from_commit: "a81d03e000",
        to_commit: "4f1c2a9000",
        pulled: [
          { version: "c9e1b07aaaa", machine: "Mac mini", files: 1, time: "2026-09-13T08:05:00Z" },
          { version: "4f1c2a9bbbb", machine: "Mac mini", files: 2, time: "2026-09-13T08:29:00Z" },
        ],
        applied: [{ path: "knowledge/notes/standup.md", status: "added" }],
        pushed: [{ path: "skills/x/SKILL.md", status: "modified" }],
      }),
    );
    expect(drawer.getByText(/^Finished · a81d03e\.\.4f1c2a9 · /)).toBeInTheDocument();
    expect(drawer.getByTestId("sync-run-snapshot")).toHaveTextContent("snap-0929-1432");
    const pulled = drawer.getByTestId("sync-run-pulled");
    expect(pulled).toHaveTextContent("c9e1b07");
    expect(pulled).toHaveTextContent("Mac mini: 1 file");
    expect(pulled).toHaveTextContent("Mac mini: 2 files");
    expect(drawer.getByTestId("sync-run-applied")).toHaveTextContent("+knowledge/notes/standup.md");
    expect(drawer.getByTestId("sync-run-pushed")).toHaveTextContent("~skills/x/SKILL.md");
    // Steps are numbered, the number in grey.
    expect(drawer.getByRole("heading", { name: "1 Safety snapshot" })).toBeInTheDocument();
    expect(drawer.getByRole("heading", { name: "3 Applied here" })).toBeInTheDocument();
    expect(drawer.getByRole("link", { name: "View in Activity" })).toHaveAttribute(
      "href",
      "/activity?tab=changes",
    );
  });

  test("says so where a step did nothing, and shows git's words for a round that failed", () => {
    const drawer = open(
      makeRound({ status: "unreachable", detail: "ssh: connect to host github.com port 22" }),
    );
    expect(drawer.getByTestId("sync-run-snapshot")).toHaveTextContent(/no snapshot/i);
    expect(drawer.getByTestId("sync-run-pushed")).toHaveTextContent(
      "Nothing from this Mac to push.",
    );
    expect(drawer.getByRole("alert")).toHaveTextContent("ssh: connect to host github.com");
    // A round that changed nothing here has nothing to roll back.
    expect(drawer.queryByRole("button", { name: /roll back/i })).toBeNull();
  });

  test("Roll back to before this round hands the round to the dialog", () => {
    const onRollback = vi.fn();
    const run = makeRound({
      id: 9,
      status: "pulled",
      snapshot: "s",
      applied: [{ path: "a.md", status: "added" }],
    });
    const drawer = open(run, onRollback);
    fireEvent.click(drawer.getByRole("button", { name: "Roll back to before this round" }));
    expect(onRollback).toHaveBeenCalledWith(run);
  });

  test("Applied here stops at five files until Show all", () => {
    const applied = Array.from({ length: 23 }, (_, i) => ({
      path: `knowledge/n${i}.md`,
      status: "added" as const,
    }));
    const drawer = open(makeRound({ status: "pulled", snapshot: "s", applied }));
    const step = within(drawer.getByTestId("sync-run-applied"));
    expect(step.getAllByRole("listitem")).toHaveLength(5);
    expect(step.getByText("Showing 5 of 23")).toBeInTheDocument();
    fireEvent.click(step.getByRole("button", { name: "Show all" }));
    expect(step.getAllByRole("listitem")).toHaveLength(23);
  });

  test("previous and next step through the table's rows", () => {
    const a = makeRound({ id: 1, finished_at: "2026-09-13T09:00:04Z" });
    const b = makeRound({ id: 2, finished_at: "2026-09-13T10:00:04Z" });
    const rows = [
      { kind: "run" as const, id: "1", run: a },
      { kind: "run" as const, id: "2", run: b },
    ];
    const onOpen = vi.fn();
    render(
      <MemoryRouter>
        <SyncRunDetail
          row={rows[0]}
          rows={rows}
          onClose={vi.fn()}
          onOpen={onOpen}
          onRollback={vi.fn()}
        />
      </MemoryRouter>,
    );
    const drawer = within(screen.getByRole("dialog"));
    expect(drawer.getByRole("button", { name: "Previous" })).toBeDisabled();
    fireEvent.click(drawer.getByRole("button", { name: "Next" }));
    expect(onOpen).toHaveBeenCalledWith(rows[1]);
  });

  acceptance("vault-sync", "expanding a file in the drawer shows its diff", () => {
    diffResult({
      path: "knowledge/a.md",
      side: "applied",
      kind: "text",
      diff: "--- before/a\n+++ after/a\n@@ -1,2 +1,2 @@\n keep\n-old\n+new\n",
      added: 1,
      removed: 1,
    });
    const drawer = open(
      makeRound({
        status: "pulled",
        snapshot: "s",
        applied: [{ path: "knowledge/a.md", status: "modified" }],
      }),
    );
    const toggle = drawer.getByRole("button", { name: "Show changes to knowledge/a.md" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(drawer.queryByTestId("sync-round-diff")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const table = within(drawer.getByTestId("sync-round-diff"));
    expect(table.getByText("new")).toBeInTheDocument();
    expect(table.getByText("old")).toBeInTheDocument();
    expect(drawer.getByText("+1")).toBeInTheDocument();
    expect(drawer.getByText("−1")).toBeInTheDocument();
  });

  test("a secret file says its contents are not shown", () => {
    diffResult({ path: "secret/x.enc", side: "pushed", kind: "secret", added: 0, removed: 0 });
    const drawer = open(
      makeRound({
        status: "pushed",
        pushed: [{ path: "secret/x.enc", status: "added" }],
      }),
    );
    fireEvent.click(drawer.getByRole("button", { name: "Show changes to secret/x.enc" }));
    expect(drawer.getByText("Encrypted — contents not shown")).toBeInTheDocument();
    expect(drawer.queryByTestId("sync-round-diff")).toBeNull();
  });
});
