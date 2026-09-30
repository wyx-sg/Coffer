// frontend/src/pages/sync/SyncConflictCard.test.tsx
//
// A round stopped on conflicting files is answered file by file, then
// continued. What has to hold: each answer goes to the daemon for the file it
// was given on, "Take the other's" shows what it changes before it overwrites,
// an edited copy that still has markers is refused in place, and Continue
// waits until every file is answered.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import type { ConflictFile, StoppedRound } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncConflictCard } from "./SyncConflictCard";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({
  useAnswerFile: vi.fn(),
  useOpenInEditor: vi.fn(),
  useFileVersions: vi.fn(),
  useContinueRound: vi.fn(),
}));

const hooks = await import("@/lib/hooks/useSyncStop");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

function file(path: string, over: Partial<ConflictFile> = {}): ConflictFile {
  return {
    path,
    area: "knowledge",
    reason: "both_changed",
    ours_time: "2026-09-13T08:00:00Z",
    theirs_time: "2026-09-13T08:30:00Z",
    theirs_machine: "Mac mini",
    other_path: null,
    answer: null,
    editor_path: null,
    ...over,
  };
}

function stopped(files: ConflictFile[]): StoppedRound {
  return {
    kind: "conflicts",
    raised_at: "2026-09-13T09:00:00Z",
    local: "aaa",
    remote: "bbb",
    join: null,
    files,
    unanswered: files.filter((f) => f.answer === null).length,
    hold: null,
  };
}

let answer: ReturnType<typeof vi.fn>;
let editor: ReturnType<typeof vi.fn>;
let proceed: ReturnType<typeof vi.fn>;

beforeEach(() => {
  answer = vi.fn();
  editor = vi.fn();
  proceed = vi.fn();
  mocked(hooks.useAnswerFile).mockReturnValue(idleMutation({ mutate: answer }));
  mocked(hooks.useOpenInEditor).mockReturnValue(idleMutation({ mutate: editor }));
  mocked(hooks.useContinueRound).mockReturnValue(idleMutation({ mutate: proceed }));
  mocked(hooks.useFileVersions).mockReturnValue({
    data: {
      path: "knowledge/a.md",
      ours: "mine\n",
      theirs: "theirs\n",
      base: null,
      take_theirs: "-mine\n+theirs\n",
      binary: false,
    },
    isLoading: false,
    error: null,
  });
});
afterEach(() => vi.clearAllMocks());

const row = (path: string) => within(screen.getByTestId(`conflict-${path}`));

describe("SyncConflictCard", () => {
  acceptance("vault-sync", "a conflict is shown as a banner above the runs", () => {
    render(
      <SyncConflictCard round={stopped([file("knowledge/a.md"), file("skills/x/SKILL.md")])} />,
    );
    const card = screen.getByTestId("sync-conflicts");
    expect(card).toHaveTextContent("knowledge/a.md");
    expect(card).toHaveTextContent("skills/x/SKILL.md");
    expect(row("knowledge/a.md").getByText("Mac mini")).toBeInTheDocument();
    expect(screen.getByTestId("sync-conflicts-progress")).toHaveTextContent("0 of 2 resolved");
  });

  test("Keep this Mac's answers at once, for that file", () => {
    render(<SyncConflictCard round={stopped([file("knowledge/a.md")])} />);
    fireEvent.click(row("knowledge/a.md").getByRole("button", { name: /keep this mac/i }));
    expect(answer).toHaveBeenCalledWith(
      { path: "knowledge/a.md", answer: "mine" },
      expect.anything(),
    );
  });

  test("Take the other's shows what it changes first, and answers from the dialog", () => {
    render(<SyncConflictCard round={stopped([file("knowledge/a.md")])} />);
    fireEvent.click(row("knowledge/a.md").getByRole("button", { name: /take the other/i }));
    expect(answer).not.toHaveBeenCalled();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByTestId("sync-take-theirs-diff")).toHaveTextContent("+theirs");
    fireEvent.click(dialog.getByRole("button", { name: /take the other/i }));
    expect(answer).toHaveBeenCalledWith(
      { path: "knowledge/a.md", answer: "theirs" },
      expect.anything(),
    );
  });

  test("Open in editor, then Mark resolved answers edited — and a copy with markers is refused in place", () => {
    const { rerender } = render(<SyncConflictCard round={stopped([file("knowledge/a.md")])} />);
    fireEvent.click(row("knowledge/a.md").getByRole("button", { name: /open in editor/i }));
    expect(editor).toHaveBeenCalledWith("knowledge/a.md");
    expect(row("knowledge/a.md").queryByRole("button", { name: /mark resolved/i })).toBeNull();

    // The daemon wrote the copy; the stop now carries its path.
    mocked(hooks.useAnswerFile).mockReturnValue(
      idleMutation({
        mutate: answer,
        error: new ApiError(
          "SYNC_CONFLICT_MARKERS_LEFT",
          "knowledge/a.md still has conflict markers at line 12",
        ),
      }),
    );
    rerender(
      <SyncConflictCard
        round={stopped([file("knowledge/a.md", { editor_path: "/tmp/a.conflict.md" })])}
      />,
    );
    fireEvent.click(row("knowledge/a.md").getByRole("button", { name: /mark resolved/i }));
    expect(answer).toHaveBeenCalledWith(
      { path: "knowledge/a.md", answer: "edited" },
      expect.anything(),
    );
    expect(row("knowledge/a.md").getByRole("alert")).toHaveTextContent(/line 12/);
  });

  test("Continue waits for every file, then continues the round", () => {
    const { rerender } = render(
      <SyncConflictCard
        round={stopped([file("knowledge/a.md", { answer: "mine" }), file("knowledge/b.md")])}
      />,
    );
    expect(screen.getByTestId("sync-conflicts-progress")).toHaveTextContent("1 of 2 resolved");
    expect(screen.getByRole("button", { name: /^continue$/i })).toBeDisabled();

    rerender(
      <SyncConflictCard
        round={stopped([
          file("knowledge/a.md", { answer: "mine" }),
          file("knowledge/b.md", { answer: "theirs" }),
        ])}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(proceed).toHaveBeenCalled();
  });
});
