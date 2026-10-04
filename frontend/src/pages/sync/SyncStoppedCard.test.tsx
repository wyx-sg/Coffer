// frontend/src/pages/sync/SyncStoppedCard.test.tsx
//
// The card under the Status tiles while a round is stopped: the files both
// Macs changed, each opening Resolve conflicts at that file, or the folders a
// held round would delete from, each with its share. Nothing is fetched or
// shown while the status says no round is stopped.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { StopState } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncStoppedCard } from "./SyncStoppedCard";
import { makeConflict, makeHeldRound, makeStopped } from "./syncConflictTestKit";
import { makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn() }));
vi.mock("@/lib/hooks/useSyncStop", () => ({ useSyncStop: vi.fn() }));

const { useSyncStatus } = await import("@/lib/hooks/useSync");
const { useSyncStop } = await import("@/lib/hooks/useSyncStop");

function seed(state: StopState, counts: { conflicts?: number; held?: number }) {
  vi.mocked(useSyncStatus).mockReturnValue({
    data: makeStatus(counts),
  } as unknown as ReturnType<typeof useSyncStatus>);
  vi.mocked(useSyncStop).mockReturnValue({ data: state } as unknown as ReturnType<
    typeof useSyncStop
  >);
}

const show = () =>
  render(
    <MemoryRouter>
      <SyncStoppedCard />
    </MemoryRouter>,
  );

afterEach(() => vi.clearAllMocks());

describe("SyncStoppedCard", () => {
  acceptance("vault-sync", "a conflict is shown as a banner above the runs", () => {
    const round = makeStopped([
      makeConflict("knowledge/team-runbooks/retries.md", { answer: "mine" }),
      makeConflict("skills/coffer-guide/SKILL.md"),
    ]);
    seed({ stopped: true, round }, { conflicts: 2 });
    show();

    const card = screen.getByTestId("sync-conflicts");
    expect(card).toHaveTextContent("Changed on both Macs");
    const first = screen.getByTestId("conflict-knowledge/team-runbooks/retries.md");
    expect(first).toHaveTextContent(/Knowledge · this Mac .+ · Mac mini /);
    expect(first).toHaveTextContent("Resolved");
    const second = screen.getByTestId("conflict-skills/coffer-guide/SKILL.md");
    expect(second).toHaveTextContent(/Skills · this Mac/);
    expect(second).toHaveTextContent("Unresolved");
    // Each row opens Resolve conflicts at its own file.
    expect(second).toHaveAttribute(
      "href",
      `/sync/conflicts?path=${encodeURIComponent("skills/coffer-guide/SKILL.md")}`,
    );
  });

  test("a long list of conflicts shows five and Show all opens the rest in place", () => {
    const names = ["a", "b", "c", "d", "e", "f"].map((n) => `knowledge/${n}.md`);
    seed(
      { stopped: true, round: makeStopped(names.map((n) => makeConflict(n))) },
      { conflicts: 6 },
    );
    show();
    expect(screen.queryByTestId("conflict-knowledge/f.md")).toBeNull();
    expect(screen.getByText("Showing 5 of 6")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(screen.getByTestId("conflict-knowledge/f.md")).toHaveTextContent("Unresolved");
  });

  test("a held round lists its folders with each one's share, and opens the review", () => {
    seed({ stopped: true, round: makeHeldRound() }, { held: 14 });
    show();
    const card = screen.getByTestId("sync-hold");
    const rows = within(card).getAllByRole("link");
    expect(rows[0]).toHaveTextContent("knowledge/archive/chat-bot/");
    expect(rows[0]).toHaveTextContent("12 files · 60% of the folder");
    // A whole folder is just its count.
    expect(rows[1]).toHaveTextContent("skills/pdf-tools-old/");
    expect(rows[1]).toHaveTextContent(/2 files$/);
    expect(rows[0]).toHaveAttribute("href", "/sync/deletions");
  });

  test("nothing is fetched or shown while no round is stopped", () => {
    seed({ stopped: false, round: null }, {});
    const { container } = show();
    expect(container).toBeEmptyDOMElement();
    expect(useSyncStop).toHaveBeenCalledWith(false);
  });
});
