// frontend/src/pages/sync/SyncDeletionReviewPage.test.tsx
//
// A held round has two answers, two buttons that each act at once: Delete N
// files (the view already listed what goes, so no dialog repeats it) and Keep
// the files. The files are grouped by folder in bordered lists (four, then Show
// all); the summary rides in the description line and there is no back link.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import type { StoppedRound } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncDeletionReviewPage } from "./SyncDeletionReviewPage";
import { makeHeldRound, makeHold } from "./syncConflictTestKit";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({
  useSyncStop: vi.fn(),
  useConfirmHold: vi.fn(),
  useRestoreHold: vi.fn(),
}));

const hooks = await import("@/lib/hooks/useSyncStop");
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
  confirm = succeeding();
  restore = succeeding();
  mocked(hooks.useConfirmHold).mockReturnValue(idleMutation({ mutate: confirm }));
  mocked(hooks.useRestoreHold).mockReturnValue(idleMutation({ mutate: restore }));
});
afterEach(() => vi.clearAllMocks());

describe("SyncDeletionReviewPage", () => {
  test("says who deleted how many in the description, files grouped by folder", () => {
    show(makeHeldRound());
    expect(screen.getByRole("heading", { name: "Review held deletions" })).toBeInTheDocument();
    expect(screen.getByText("Round held")).toBeInTheDocument();
    expect(
      screen.getByText(/14 files in 2 folders, deleted on Mac mini · the rest of what was pulled/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
    const [chat, pdf] = screen.getAllByTestId("sync-held-group");
    expect(within(chat!).getByRole("heading")).toHaveTextContent("Knowledge · archive/chat-bot");
    // Four paths are listed, the other eight behind Show all.
    expect(within(chat!).getAllByRole("listitem")).toHaveLength(4);
    expect(chat).toHaveTextContent("Showing 4 of 12");
    fireEvent.click(within(chat!).getByRole("button", { name: "Show all" }));
    expect(within(chat!).getAllByRole("listitem")).toHaveLength(12);
    expect(within(pdf!).getByRole("heading")).toHaveTextContent("Skills · pdf-tools-old");
    expect(pdf).toHaveTextContent("skills/pdf-tools-old/scripts/extract.py");
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
    // The files are listed by folder before any press, and no dialog is involved.
    expect(screen.getAllByTestId("sync-held-group")).toHaveLength(1);
    expect(screen.getAllByTestId("sync-held-group")[0]).toHaveTextContent("Showing 4 of 22");
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
