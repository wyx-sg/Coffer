// frontend/src/pages/sync/SyncRunDetail.test.tsx
//
// A round's drawer (6.5.04) names what its row could only count, in the four
// steps every round takes: the snapshot, the commits pulled and from whom, the
// files applied here, the files pushed — and its footer rolls it back or opens
// Activity.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { SyncRound } from "@/lib/api/sync";
import { SyncRunDetail } from "./SyncRunDetail";
import { makeRound } from "./syncTestKit";

function open(run: SyncRound, onRollback = vi.fn()) {
  render(
    <MemoryRouter>
      <SyncRunDetail
        row={{ kind: "run", id: String(run.id), run }}
        onClose={vi.fn()}
        onOpen={vi.fn()}
        onRollback={onRollback}
      />
    </MemoryRouter>,
  );
  return within(screen.getByRole("dialog"));
}

describe("SyncRunDetail", () => {
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
    expect(drawer.getByText("Finished")).toBeInTheDocument();
    expect(drawer.getByText("a81d03e..4f1c2a9")).toBeInTheDocument();
    expect(drawer.getByTestId("sync-run-snapshot")).toHaveTextContent("snap-0929-1432");
    const pulled = drawer.getByTestId("sync-run-pulled");
    expect(pulled).toHaveTextContent("c9e1b07");
    expect(pulled).toHaveTextContent("Mac mini: 1 file");
    expect(pulled).toHaveTextContent("Mac mini: 2 files");
    expect(drawer.getByTestId("sync-run-applied")).toHaveTextContent(
      "+ knowledge/notes/standup.md",
    );
    expect(drawer.getByTestId("sync-run-pushed")).toHaveTextContent("~ skills/x/SKILL.md");
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
});
