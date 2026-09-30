// frontend/src/pages/sync/SyncJoinCard.test.tsx
//
// A join is stated before it is made: what comes down by area, how many files
// are the same, which differ, what goes up, and that nothing is deleted. An
// empty remote receives the whole vault; a refused join says why and offers no
// button. The files a join left differing are answered per file or all at once.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { ConflictFile, JoinPreview } from "@/lib/api/sync";
import { SyncJoinCard } from "./SyncJoinCard";
import { SyncJoinChoices } from "./SyncJoinChoices";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({
  useJoinPreview: vi.fn(),
  useJoin: vi.fn(),
  useJoinChoices: vi.fn(),
  useChooseJoin: vi.fn(),
}));

const hooks = await import("@/lib/hooks/useSyncStop");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

function preview(over: Partial<JoinPreview> = {}): JoinPreview {
  return {
    kind: "new",
    remote_tip: "abc",
    pushed_by: "Mac mini",
    pushed_at: "2026-09-13T08:00:00Z",
    pulled: [{ area: "knowledge", files: 12 }],
    same: 30,
    differ: ["knowledge/notes/a.md"],
    pushed: [{ area: "skills", files: 2 }],
    deleted: [],
    conflicts: [],
    same_name: [],
    refused: null,
    pulled_files: 12,
    pushed_files: 2,
    ...over,
  };
}

function seedPreview(data: JoinPreview) {
  mocked(hooks.useJoinPreview).mockReturnValue({ data, isLoading: false, error: null });
}

let join: ReturnType<typeof vi.fn>;
let choose: ReturnType<typeof vi.fn>;

beforeEach(() => {
  join = vi.fn();
  choose = vi.fn();
  mocked(hooks.useJoin).mockReturnValue(idleMutation({ mutate: join }));
  mocked(hooks.useChooseJoin).mockReturnValue(idleMutation({ mutate: choose }));
});
afterEach(() => vi.clearAllMocks());

describe("SyncJoinCard", () => {
  test("states the join before making it, then joins", () => {
    seedPreview(preview());
    render(<SyncJoinCard />);
    const shown = screen.getByTestId("sync-join-preview");
    expect(within(shown).getByTestId("sync-join-pulled")).toHaveTextContent("knowledge · 12");
    expect(shown).toHaveTextContent(/30 files are already the same/);
    expect(within(shown).getByTestId("sync-join-differ")).toHaveTextContent("knowledge/notes/a.md");
    expect(within(shown).getByTestId("sync-join-pushed")).toHaveTextContent("skills · 2");
    expect(shown).toHaveTextContent(/nothing is deleted/i);

    fireEvent.click(screen.getByRole("button", { name: /^join$/i }));
    expect(join).toHaveBeenCalled();
  });

  test("an empty remote says it receives this whole vault", () => {
    seedPreview(preview({ kind: "empty", pulled: [], differ: [], pushed_by: null }));
    render(<SyncJoinCard />);
    expect(screen.getByTestId("sync-join-preview")).toHaveTextContent(/empty/i);
    expect(screen.getByTestId("sync-join-preview")).toHaveTextContent(/whole vault/i);
  });

  test("a refused join says why and cannot be clicked", () => {
    seedPreview(preview({ refused: "The remote is at layout 3; this build writes layout 4." }));
    render(<SyncJoinCard />);
    expect(screen.getByRole("alert")).toHaveTextContent(/layout 3/);
    expect(screen.getByRole("button", { name: /^join$/i })).toBeDisabled();
  });
});

describe("SyncJoinChoices", () => {
  const differing = (path: string): ConflictFile => ({
    path,
    area: "knowledge",
    reason: "join_differs",
    ours_time: null,
    theirs_time: null,
    theirs_machine: null,
    other_path: null,
    answer: null,
    editor_path: null,
  });

  beforeEach(() => {
    mocked(hooks.useJoinChoices).mockReturnValue({
      data: { files: [differing("knowledge/a.md"), differing("knowledge/b.md")] },
    });
  });

  test("answers one file, or all of them", () => {
    render(<SyncJoinChoices />);
    const row = within(screen.getByTestId("join-choice-knowledge/a.md"));
    fireEvent.click(row.getByRole("button", { name: /take theirs/i }));
    expect(choose).toHaveBeenLastCalledWith([{ path: "knowledge/a.md", answer: "theirs" }]);

    fireEvent.click(screen.getByRole("button", { name: /keep mine for all/i }));
    expect(choose).toHaveBeenLastCalledWith([
      { path: "knowledge/a.md", answer: "mine" },
      { path: "knowledge/b.md", answer: "mine" },
    ]);
  });
});
