// frontend/src/pages/sync/SyncRunDetail.test.tsx
//
// A round opened up names what its row could only count: the snapshot it took,
// each commit it pulled and from whom, each file it changed here and pushed.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { SyncRunDetail } from "./SyncRunDetail";
import { makeRound } from "./syncTestKit";

describe("SyncRunDetail", () => {
  test("names the snapshot, the pulled commits and the files moved each way", () => {
    render(
      <SyncRunDetail
        run={makeRound({
          status: "pulled_and_pushed",
          snapshot: "sync/pre-round/42",
          pulled: [
            {
              version: "0123456789abcdef",
              machine: "Mac mini",
              files: 2,
              time: "2026-09-13T08:00:00Z",
            },
          ],
          applied: [
            { path: "knowledge/notes/a.md", status: "modified" },
            { path: "skills/old/SKILL.md", status: "removed" },
          ],
          pushed: [{ path: "resources/channel/seatalk.yaml", status: "added" }],
        })}
      />,
    );

    expect(screen.getByTestId("sync-run-snapshot")).toHaveTextContent("sync/pre-round/42");
    const pulled = screen.getByTestId("sync-run-pulled");
    expect(pulled).toHaveTextContent("0123456");
    expect(pulled).toHaveTextContent("Mac mini");
    expect(screen.getByTestId("sync-run-applied")).toHaveTextContent("~ knowledge/notes/a.md");
    expect(screen.getByTestId("sync-run-applied")).toHaveTextContent("− skills/old/SKILL.md");
    expect(screen.getByTestId("sync-run-pushed")).toHaveTextContent(
      "+ resources/channel/seatalk.yaml",
    );
    expect(screen.queryByText(/nothing further/i)).not.toBeInTheDocument();
  });

  test("a failed round shows git's own words", () => {
    render(
      <SyncRunDetail
        run={makeRound({ status: "push_failed", detail: "rejected (fetch first)" })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("rejected (fetch first)");
  });

  test("a quiet round says there is nothing further", () => {
    render(<SyncRunDetail run={makeRound()} />);
    expect(screen.getByText(/nothing further/i)).toBeInTheDocument();
  });
});
