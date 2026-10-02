// frontend/src/pages/sync/SyncDeletionReviewPage.test.tsx
//
// A held round has two answers, each naming how many files it touches:
// Delete (asked again, because it destroys, stating the files, who deleted
// them and the snapshot) and Restore (at once). The files are grouped by
// folder with each folder's share, so 12 of 20 and 2 of 2 never read alike.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { StoppedRound } from "@/lib/api/sync";
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
  test("says who deleted how many, grouped by folder with its share", () => {
    show(makeHeldRound());
    expect(screen.getByRole("heading", { name: "Review held deletions" })).toBeInTheDocument();
    expect(screen.getByText("Round held")).toBeInTheDocument();
    expect(screen.getByTestId("sync-deletions-summary")).toHaveTextContent(
      "14 files2 foldersdeleted on Mac mini",
    );
    const [chat, pdf] = screen.getAllByTestId("sync-held-group");
    expect(within(chat!).getByRole("heading")).toHaveTextContent("Knowledge · archive/chat-bot");
    // Six paths are listed, the other six counted.
    expect(within(chat!).getAllByRole("listitem")).toHaveLength(7);
    expect(chat).toHaveTextContent("…and 6 more");
    expect(within(pdf!).getByRole("heading")).toHaveTextContent("Skills · pdf-tools-old");
    expect(pdf).toHaveTextContent("skills/pdf-tools-old/scripts/extract.py");
  });

  test("Delete asks first, stating what it takes, then confirms the hold and goes back", () => {
    show(makeHeldRound());
    fireEvent.click(screen.getByRole("button", { name: "Delete 14 files…" }));
    expect(confirm).not.toHaveBeenCalled();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("Delete 14 files on this Mac too?")).toBeInTheDocument();
    expect(dialog.getByText(/14 in 2 folders/)).toBeInTheDocument();
    expect(
      dialog.getByText("knowledge/archive/chat-bot/, skills/pdf-tools-old/"),
    ).toBeInTheDocument();
    expect(dialog.getByText("Taken before deleting")).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Delete 14 files" }));
    expect(confirm).toHaveBeenCalled();
    expect(screen.getByText("Sync home")).toBeInTheDocument();
  });

  test("Restore keeps the files at once — it destroys nothing", () => {
    show(makeHeldRound());
    fireEvent.click(screen.getByRole("button", { name: "Restore 14 files" }));
    expect(restore).toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByText("Sync home")).toBeInTheDocument();
  });

  test("a hold this Mac would push out is worded for this Mac", () => {
    show(makeHeldRound(makeHold({ direction: "outgoing", machines: ["Laptop"] })));
    expect(screen.getByTestId("sync-deletions-summary")).toHaveTextContent("deleted on this Mac");
    expect(screen.getByText("Delete on the other Macs too")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete 14 files…" }));
    expect(
      within(screen.getByRole("dialog")).getByText("Delete 14 files on every Mac?"),
    ).toBeInTheDocument();
  });

  test("with no held round there is nothing to review", () => {
    show(null);
    expect(screen.getByText("Nothing is held")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });
});
