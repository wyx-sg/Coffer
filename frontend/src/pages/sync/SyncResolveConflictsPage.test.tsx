// frontend/src/pages/sync/SyncResolveConflictsPage.test.tsx
//
// Resolve conflicts, answered file by file and then continued. What has to
// hold: picking a choice records it for that file, and what it changes here
// shows under the cards (the diff, with line numbers, or "nothing changes");
// the editor path answers `edited` and a copy with markers left is refused in
// place; Continue waits for every file; an encrypted secret offers only the
// two choices; and "Merge with an agent" carries the backend's prompt for the
// files an agent may merge, recorded with "I merged it".
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import type { StoppedRound } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncResolveConflictsPage } from "./SyncResolveConflictsPage";
import { makeConflict, makeStopped, makeVersions } from "./syncConflictTestKit";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({
  useSyncStop: vi.fn(),
  useAnswerFile: vi.fn(),
  useOpenInEditor: vi.fn(),
  useFileVersions: vi.fn(),
  useContinueRound: vi.fn(),
  useMarkMerged: vi.fn(),
}));
// The hand-off's own buttons are tested with it; here it shows what it was given.
vi.mock("@/components/handoff/AgentHandoff", () => ({
  AgentHandoff: ({ prompt }: { prompt: string }) => <div data-testid="handoff">{prompt}</div>,
}));

const hooks = await import("@/lib/hooks/useSyncStop");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;
/** A mutate that succeeds at once, running the caller's onSuccess. */
const succeeding = () =>
  vi.fn((_: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());

const SKILL = "skills/coffer-guide/SKILL.md";
const NOTE = "knowledge/team-runbooks/retries.md";
const SECRET = "secret/sync.PUSH_TOKEN.enc";

let answer: ReturnType<typeof vi.fn>;
let editor: ReturnType<typeof vi.fn>;
let proceed: ReturnType<typeof vi.fn>;
let merged: ReturnType<typeof vi.fn>;

function seed(round: StoppedRound, { edited = null as string | null } = {}) {
  mocked(hooks.useSyncStop).mockReturnValue({ data: { stopped: true, round }, isLoading: false });
  mocked(hooks.useFileVersions).mockImplementation((path: string) => ({
    data: makeVersions(path, { edited }),
    isLoading: false,
    error: null,
  }));
}

function show(path?: string) {
  const at = path ? `/sync/conflicts?path=${encodeURIComponent(path)}` : "/sync/conflicts";
  return render(
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route path="/sync/conflicts" element={<SyncResolveConflictsPage />} />
        <Route path="/sync" element={<p>Sync home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  answer = vi.fn();
  editor = succeeding();
  proceed = succeeding();
  merged = vi.fn();
  mocked(hooks.useAnswerFile).mockReturnValue(idleMutation({ mutate: answer }));
  mocked(hooks.useOpenInEditor).mockReturnValue(idleMutation({ mutate: editor }));
  mocked(hooks.useContinueRound).mockReturnValue(idleMutation({ mutate: proceed }));
  mocked(hooks.useMarkMerged).mockReturnValue(idleMutation({ mutate: merged }));
});
afterEach(() => vi.clearAllMocks());

const files = () => within(screen.getByRole("navigation", { name: /conflicting files/i }));

describe("SyncResolveConflictsPage", () => {
  test("lists every file with its answer, and opens the one the URL names", () => {
    seed(makeStopped([makeConflict(NOTE, { answer: "mine" }), makeConflict(SKILL)]));
    show(SKILL);
    expect(screen.getByRole("heading", { name: "Resolve conflicts" })).toBeInTheDocument();
    expect(screen.getByText("Pushing blocked")).toBeInTheDocument();
    expect(files().getByTestId(`conflict-file-${NOTE}`)).toHaveTextContent("Kept this Mac’s");
    expect(files().getByTestId(`conflict-file-${SKILL}`)).toHaveTextContent("Choose a version");
    expect(screen.getByTestId(`conflict-pane-${SKILL}`)).toHaveTextContent(
      /Skills · changed here at .+ by you, and on Mac mini at/,
    );
  });

  test("picking a version records it for that file", () => {
    seed(makeStopped([makeConflict(SKILL)]));
    show();
    fireEvent.click(screen.getByRole("radio", { name: "Take Mac mini’s" }));
    expect(answer).toHaveBeenCalledWith({ path: SKILL, answer: "theirs" });
    fireEvent.click(screen.getByRole("radio", { name: "Keep this Mac’s" }));
    expect(answer).toHaveBeenCalledWith({ path: SKILL, answer: "mine" });
  });

  test("taking theirs shows the diff with line numbers; keeping mine says nothing changes", () => {
    seed(makeStopped([makeConflict(SKILL, { answer: "theirs" })]));
    const { unmount } = show();
    expect(files().getByTestId(`conflict-file-${SKILL}`)).toHaveTextContent(
      "Take Mac mini’s · not applied yet",
    );
    const diff = screen.getByTestId("sync-conflict-diff");
    expect(diff).toHaveTextContent("@@ −14,4 +14,4 @@");
    const removed = diff.querySelector('[data-line="remove"]');
    expect(removed).toHaveTextContent(/^15.*Load it before asking\.$/);
    expect(diff.querySelector('[data-line="add"]')).toHaveTextContent(/^15.*Load it first\.$/);
    unmount();

    seed(makeStopped([makeConflict(SKILL, { answer: "mine" })]));
    show();
    expect(screen.queryByTestId("sync-conflict-diff")).toBeNull();
    expect(
      screen.getByText(
        "Nothing changes on this Mac. Mac mini gets this Mac’s version in the next push.",
      ),
    ).toBeInTheDocument();
  });

  test("Open in editor, then Mark resolved answers edited — a copy with markers is refused in place", () => {
    seed(makeStopped([makeConflict(SKILL)]), { edited: "<<<<<<< this Mac\nmine\n=======\n" });
    mocked(hooks.useAnswerFile).mockReturnValue(
      idleMutation({
        mutate: answer,
        error: new ApiError(
          "SYNC_CONFLICT_MARKERS_LEFT",
          `Line 15 of ${SKILL} still has conflict markers. Remove them, save, then mark it resolved.`,
        ),
      }),
    );
    show();
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    expect(editor).toHaveBeenCalledWith(SKILL, expect.anything());
    expect(files().getByTestId(`conflict-file-${SKILL}`)).toHaveTextContent(
      "Editing in your editor",
    );
    expect(screen.getByTestId("sync-conflict-saved")).toHaveTextContent("<<<<<<< this Mac");
    expect(hooks.useFileVersions).toHaveBeenCalledWith(SKILL, true, { live: true });

    fireEvent.click(screen.getByRole("button", { name: "Mark resolved" }));
    expect(answer).toHaveBeenCalledWith({ path: SKILL, answer: "edited" });
    expect(screen.getByRole("alert")).toHaveTextContent(/Line 15 .* still has conflict markers/);

    fireEvent.click(screen.getByRole("button", { name: "Back to two choices" }));
    expect(screen.getByRole("radio", { name: "Keep this Mac’s" })).toBeInTheDocument();
  });

  test("Continue round waits for every file, then continues and goes back to Sync", () => {
    seed(makeStopped([makeConflict(NOTE, { answer: "mine" }), makeConflict(SKILL)]));
    const { unmount } = show();
    expect(screen.getByTestId("sync-conflicts-progress")).toHaveTextContent(
      "1 of 2 files resolved · continue is available when every file has a version",
    );
    expect(screen.getByRole("button", { name: "Continue round" })).toBeDisabled();
    unmount();

    seed(
      makeStopped([
        makeConflict(NOTE, { answer: "mine" }),
        makeConflict(SKILL, { answer: "edited" }),
      ]),
    );
    show(SKILL);
    expect(screen.getByText(/Resolved in your editor/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue round" }));
    expect(proceed).toHaveBeenCalled();
    expect(screen.getByText("Sync home")).toBeInTheDocument();
  });

  acceptance("vault-sync", "an encrypted secret in conflict offers only the two choices", () => {
    seed(
      makeStopped([makeConflict(SECRET, { area: "secret", secret: true })], {
        handoff: { prompt: "merge these" },
      }),
    );
    show();
    const pane = within(screen.getByTestId(`conflict-pane-${SECRET}`));
    expect(pane.getAllByRole("radio")).toHaveLength(2);
    expect(pane.queryByRole("button", { name: /open in editor/i })).toBeNull();
    expect(pane.queryByTestId("sync-conflict-merge")).toBeNull();
    expect(pane.getByTestId("sync-conflict-secret")).toHaveTextContent(
      /encrypted secret: its contents are not shown/,
    );

    // Even with theirs picked, no diff of its contents is fetched or shown.
    seed(makeStopped([makeConflict(SECRET, { area: "secret", secret: true, answer: "theirs" })]));
    show();
    expect(screen.queryByTestId("sync-conflict-diff")).toBeNull();
    expect(hooks.useFileVersions).not.toHaveBeenCalled();
  });

  acceptance(
    "vault-sync",
    "a conflict's merge is handed to an agent and recorded with I merged it",
    () => {
      const prompt = "A Coffer sync round stopped on 1 file … Marked-up copy to edit: /tmp/x";
      seed(
        makeStopped([makeConflict(SKILL, { agent_merge: true }), makeConflict(NOTE)], {
          handoff: { prompt },
        }),
      );
      mocked(hooks.useMarkMerged).mockReturnValue(
        idleMutation({
          mutate: merged,
          error: new ApiError(
            "SYNC_CONFLICT_MARKERS_LEFT",
            `Line 3 of ${SKILL} still has conflict markers. Remove them, save, then mark it resolved.`,
          ),
        }),
      );
      const { unmount } = show(SKILL);
      const block = within(screen.getByTestId("sync-conflict-merge"));
      expect(block.getByText("Merge with an agent")).toBeInTheDocument();
      expect(block.getByText(/edits the marked-up copies; Coffer commits/)).toBeInTheDocument();
      expect(block.getByTestId("handoff")).toHaveTextContent(prompt);
      fireEvent.click(block.getByRole("button", { name: "I merged it" }));
      expect(merged).toHaveBeenCalled();
      expect(block.getByRole("alert")).toHaveTextContent(/Line 3 .* still has conflict markers/);
      unmount();

      // A file the agent is not handed has no merge block.
      show(NOTE);
      expect(screen.queryByTestId("sync-conflict-merge")).toBeNull();
      expect(screen.queryByTestId("handoff")).toBeNull();
    },
  );
});
