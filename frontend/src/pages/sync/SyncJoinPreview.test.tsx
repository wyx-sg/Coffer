// frontend/src/pages/sync/SyncJoinPreview.test.tsx
//
// A join is stated before it is made (6.5.18): what comes down by area, how
// many files are the same, how many differ (left alone until chosen), what
// goes up, and that nothing is deleted. A refused join says why and offers no
// Join button.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { JoinPreview } from "@/lib/api/sync";
import { SyncJoinPreview } from "./SyncJoinPreview";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({ useJoinPreview: vi.fn(), useJoin: vi.fn() }));

const hooks = await import("@/lib/hooks/useSyncStop");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

function preview(over: Partial<JoinPreview> = {}): JoinPreview {
  return {
    kind: "new",
    remote_tip: "abc",
    pushed_by: "Mac mini",
    pushed_at: "2026-09-13T08:00:00Z",
    pulled: [
      { area: "knowledge", files: 96 },
      { area: "resources/mcp_server", files: 8 },
      { area: "resources/custom_tool", files: 4 },
      { area: "skills", files: 30 },
    ],
    same: 74,
    differ: ["knowledge/a.md", "skills/x/SKILL.md"],
    pushed: [{ area: "skills", files: 22 }],
    deleted: [],
    conflicts: [],
    same_name: [],
    refused: null,
    pulled_files: 138,
    pushed_files: 22,
    ...over,
  };
}

let join: ReturnType<typeof vi.fn>;
const onBack = vi.fn();
const seed = (data: JoinPreview) =>
  mocked(hooks.useJoinPreview).mockReturnValue({ data, isLoading: false, error: null });

beforeEach(() => {
  join = vi.fn();
  mocked(hooks.useJoin).mockReturnValue(idleMutation({ mutate: join }));
});
afterEach(() => vi.clearAllMocks());

describe("SyncJoinPreview", () => {
  test("states the join before making it, then joins", () => {
    seed(preview());
    render(<SyncJoinPreview onBack={onBack} backPending={false} />);
    expect(screen.getByText("The repository already holds a vault")).toBeInTheDocument();
    expect(screen.getByText(/Pushed by Mac mini/)).toBeInTheDocument();
    const shown = within(screen.getByTestId("sync-join-preview"));
    expect(shown.getByTestId("sync-join-pulled")).toHaveTextContent("138 files are pulled in");
    expect(shown.getByTestId("sync-join-pulled")).toHaveTextContent(
      "Knowledge 96 · Skills 30 · MCP servers & tools 12",
    );
    expect(shown.getByText("74 files are already the same")).toBeInTheDocument();
    expect(shown.getByTestId("sync-join-differ")).toHaveTextContent(
      "2 files differ from this Mac’s copy",
    );
    expect(shown.getByTestId("sync-join-pushed")).toHaveTextContent(
      "22 files only this Mac has are pushed",
    );
    expect(shown.getByTestId("sync-join-pushed")).toHaveTextContent("Mac mini gets them");
    expect(shown.getByText("Nothing is deleted")).toBeInTheDocument();
    expect(screen.getByText("A safety snapshot is taken first")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Join and pull" }));
    expect(join).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(onBack).toHaveBeenCalled();
  });

  test("no differing files, no differ line", () => {
    seed(preview({ differ: [] }));
    render(<SyncJoinPreview onBack={onBack} backPending={false} />);
    expect(screen.queryByTestId("sync-join-differ")).not.toBeInTheDocument();
  });

  test("a refused join says why and cannot be clicked", () => {
    seed(preview({ refused: "The remote is at layout 3; this build writes layout 4." }));
    render(<SyncJoinPreview onBack={onBack} backPending={false} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/layout 3/);
    expect(screen.getByRole("button", { name: "Join and pull" })).toBeDisabled();
  });
});
