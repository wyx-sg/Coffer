// frontend/src/pages/sync/SyncDeletionReviewPage.test.tsx
//
// A held round has two answers, two buttons that each act at once: Delete N
// files (the page already showed what goes, so no dialog repeats it) and Keep
// the files. The shared review shape: every held file down the left, folder by
// folder; the chosen one's text, as the lines a delete removes, on the right.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import type { StoppedRound } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncDeletionReviewPage } from "./SyncDeletionReviewPage";
import { makeHeldRound, makeHold } from "./syncConflictTestKit";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ useHeldFileDiff: vi.fn() }));
vi.mock("@/lib/hooks/useSyncStop", () => ({
  useSyncStop: vi.fn(),
  useConfirmHold: vi.fn(),
  useRestoreHold: vi.fn(),
}));

const hooks = await import("@/lib/hooks/useSyncStop");
const syncHooks = await import("@/lib/hooks/useSync");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;
const succeeding = () =>
  vi.fn((_: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());

let confirm: ReturnType<typeof vi.fn>;
let restore: ReturnType<typeof vi.fn>;

function show(round: StoppedRound | null) {
  mocked(hooks.useSyncStop).mockReturnValue({
    data: { stopped: round !== null, round },
    isLoading: false,
  });
  return render(
    <MemoryRouter initialEntries={["/sync/deletions"]}>
      <Routes>
        <Route path="/sync/deletions" element={<SyncDeletionReviewPage />} />
        <Route path="/sync" element={<p>Sync home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocked(syncHooks.useHeldFileDiff).mockImplementation((path: string) => ({
    isLoading: false,
    error: null,
    data: {
      path,
      side: "held",
      kind: "text",
      diff: `--- before/${path}\n+++ after/${path}\n@@ -1,2 +0,0 @@\n-first line\n-second line\n`,
      added: 0,
      removed: 2,
    },
  }));
  confirm = succeeding();
  restore = succeeding();
  mocked(hooks.useConfirmHold).mockReturnValue(idleMutation({ mutate: confirm }));
  mocked(hooks.useRestoreHold).mockReturnValue(idleMutation({ mutate: restore }));
});
afterEach(() => vi.clearAllMocks());

describe("SyncDeletionReviewPage", () => {
  test("says who deleted how many; every held file is listed, the chosen one's text shown", () => {
    show(makeHeldRound());
    expect(screen.getByRole("heading", { name: "Review held deletions" })).toBeInTheDocument();
    expect(screen.getByText("Round held")).toBeInTheDocument();
    expect(
      screen.getByText(/14 files in 2 folders, deleted on Mac mini · the rest of what was pulled/),
    ).toBeInTheDocument();
    const nav = screen.getByRole("navigation");
    expect(within(nav).getAllByRole("button")).toHaveLength(14);
    expect(screen.getByTestId("held-file-knowledge/archive/chat-bot/n1.md")).toHaveTextContent(
      "Knowledge · archive/chat-bot",
    );
    // The first file is open, its whole text as removed lines.
    const pane = screen.getByTestId("sync-review-pane");
    expect(pane).toHaveTextContent("knowledge/archive/chat-bot/n1.md");
    expect(pane).toHaveTextContent("Deleted on Mac mini");
    expect(within(pane).getByTestId("sync-review-diff")).toHaveTextContent("second line");
    fireEvent.click(screen.getByTestId("held-file-skills/pdf-tools-old/scripts/extract.py"));
    expect(screen.getByTestId("sync-review-pane")).toHaveTextContent(
      "skills/pdf-tools-old/scripts/extract.py",
    );
    expect(syncHooks.useHeldFileDiff).toHaveBeenLastCalledWith(
      "skills/pdf-tools-old/scripts/extract.py",
      true,
    );
  });

  acceptance("vault-sync", "the held deletions view answers with one press", () => {
    const paths = Array.from({ length: 22 }, (_, i) => `knowledge/archive/n${i + 1}.md`);
    const hold = makeHold({
      direction: "outgoing",
      machines: [],
      paths,
      groups: [{ folder: "knowledge/archive", paths, total: 30 }],
    });
    const { unmount } = show(makeHeldRound(hold));
    // Every file can be read before any press, and no dialog is involved.
    expect(within(screen.getByRole("navigation")).getAllByRole("button")).toHaveLength(22);
    fireEvent.click(screen.getByRole("button", { name: "Delete 22 files" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(restore).not.toHaveBeenCalled();
    expect(screen.getByText("Sync home")).toBeInTheDocument();
    unmount();

    show(makeHeldRound(hold));
    fireEvent.click(screen.getByRole("button", { name: "Keep the files" }));
    expect(restore).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Sync home")).toBeInTheDocument();
  });

  test("a refusal shows in place and stays on the page", () => {
    confirm = vi.fn();
    mocked(hooks.useConfirmHold).mockReturnValue(
      idleMutation({
        mutate: confirm,
        error: new ApiError("SYNC_NOTHING_STOPPED", "Nothing is held."),
      }),
    );
    show(makeHeldRound());
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete 14 files" }));
    expect(confirm).toHaveBeenCalled();
    expect(screen.queryByText("Sync home")).toBeNull();
  });

  test("a hold this Mac would push out is worded for this Mac", () => {
    show(makeHeldRound(makeHold({ direction: "outgoing", machines: ["Laptop"] })));
    expect(
      screen.getByText(/deleted on this Mac · nothing is pushed until you decide/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Delete removes them on the remote and every other Mac/),
    ).toBeInTheDocument();
  });

  test("with no held round there is nothing to review", () => {
    show(null);
    expect(screen.getByText("Nothing is held")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });
});
