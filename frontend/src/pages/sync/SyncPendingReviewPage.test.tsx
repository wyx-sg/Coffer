// frontend/src/pages/sync/SyncPendingReviewPage.test.tsx
//
// What waits to push is reviewed on its own page: one entry per file however
// many commits touched it, the chosen file's change since the last push on the
// right, and Push now to run the round at once.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { SyncPendingReviewPage } from "./SyncPendingReviewPage";
import { idleMutation, makeStatus } from "./syncTestKit";
import { clock } from "./syncTime";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: vi.fn(),
  useRunSync: vi.fn(),
  usePendingFileDiff: vi.fn(),
}));

const hooks = await import("@/lib/hooks/useSync");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const T1 = "2026-10-05T08:26:00Z";
const T2 = "2026-10-05T08:36:00Z";
const DOC = "resources/channel/seatalk.json";

let run: ReturnType<typeof vi.fn>;

function show(waiting = makeStatus().waiting) {
  mocked(hooks.useSyncStatus).mockReturnValue({
    data: makeStatus({ waiting, next_round_at: "2026-10-05T09:15:00Z" }),
    isPending: false,
  });
  return render(
    <MemoryRouter initialEntries={["/sync/pending"]}>
      <Routes>
        <Route path="/sync/pending" element={<SyncPendingReviewPage />} />
        <Route path="/sync" element={<p>Sync home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const commit = (time: string, writer: string, path: string, status = "modified") => ({
  version: `v-${time}-${path}`,
  time,
  writer,
  summary: "",
  changes: [{ path, status: status as "modified" | "added" | "removed" }],
});

beforeEach(() => {
  run = vi.fn((_: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
  mocked(hooks.useRunSync).mockReturnValue(idleMutation({ mutate: run }));
  mocked(hooks.usePendingFileDiff).mockImplementation((path: string) => ({
    isLoading: false,
    error: null,
    data: {
      path,
      side: "pending",
      kind: "text",
      diff: `--- before/${path}\n+++ after/${path}\n@@ -1 +1 @@\n-old ${path}\n+new ${path}\n`,
      added: 1,
      removed: 1,
    },
  }));
});
afterEach(() => vi.clearAllMocks());

describe("SyncPendingReviewPage", () => {
  acceptance("vault-sync", "a waiting file shows its change since the last push", () => {
    // Newest first, as the status lists them: four saves of one file are one entry.
    show([
      commit(T2, "daemon", "state/channel-peers/seatalk.json"),
      commit(T1, "user", DOC),
      commit(T1, "user", DOC),
      commit(T1, "user", DOC),
      commit(T1, "agent", "knowledge/new.md", "added"),
    ]);
    expect(screen.getByRole("heading", { name: "Review changes to push" })).toBeInTheDocument();
    expect(
      screen.getByText(/3 files on this Mac the remote does not have yet/),
    ).toBeInTheDocument();
    const nav = screen.getByRole("navigation");
    expect(within(nav).getAllByRole("button")).toHaveLength(3);
    expect(screen.getByTestId(`pending-file-${DOC}`)).toHaveTextContent(`You · ${clock(T1)}`);
    expect(screen.getByTestId("pending-file-knowledge/new.md")).toHaveTextContent("+");

    // The first file is open; a click opens another.
    const pane = () => screen.getByTestId("sync-review-pane");
    expect(pane()).toHaveTextContent("state/channel-peers/seatalk.json");
    expect(pane()).toHaveTextContent(`Coffer · ${clock(T2)}`);
    fireEvent.click(screen.getByTestId(`pending-file-${DOC}`));
    expect(within(pane()).getByTestId("sync-review-diff")).toHaveTextContent(`new ${DOC}`);
    expect(hooks.usePendingFileDiff).toHaveBeenLastCalledWith(DOC, true);
  });

  test("Push now runs the round and goes back to Sync", () => {
    show([commit(T1, "user", DOC)]);
    fireEvent.click(screen.getByRole("button", { name: "Push now" }));
    expect(run).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Sync home")).toBeInTheDocument();
  });

  test("nothing waiting: nothing to review", () => {
    show([]);
    expect(screen.getByText("Nothing waits to push")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Push now" })).toBeNull();
  });
});
