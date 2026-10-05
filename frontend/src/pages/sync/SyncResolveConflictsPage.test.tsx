// frontend/src/pages/sync/SyncResolveConflictsPage.test.tsx
//
// Resolve conflicts, answered file by file and then continued. What has to
// hold: picking a choice records it for that file, and what it changes here
// shows under the cards (the diff, with line numbers, or "nothing changes");
// the editor path answers `edited` and a copy with markers left is refused in
// place; Continue waits for every file; an encrypted secret offers only the
// two choices; an agent is asked for one file or for the join's, and its merge
// is checked and marked resolved by the person; and `?mode=join` is the same
// page ending in Apply choices.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import type { ConflictFile, StoppedRound } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncResolveConflictsPage } from "./SyncResolveConflictsPage";
import { makeConflict, makeStopped, makeVersions } from "./syncConflictTestKit";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({
  useSyncStop: vi.fn(),
  useAnswerFile: vi.fn(),
  useOpenInEditor: vi.fn(),
  useDiscardCopy: vi.fn(),
  useHandoffRequest: vi.fn(),
  useFileVersions: vi.fn(),
  useContinueRound: vi.fn(),
  useJoinChoices: vi.fn(),
  useChooseJoin: vi.fn(),
}));
// The hand-off's own buttons are tested with it; here it asks for its prompt
// the way it does, when the person picks Hand off to Claude Code.
vi.mock("@/components/handoff/AgentHandoff", () => ({
  AgentHandoff: ({
    prompt,
  }: {
    prompt: string | ((t: { agent: string | null }) => Promise<string>);
  }) => (
    <button
      type="button"
      onClick={() => typeof prompt !== "string" && void prompt({ agent: "Claude Code" })}
    >
      Hand off to Claude Code
    </button>
  ),
}));

const hooks = await import("@/lib/hooks/useSyncStop");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;
/** A mutate that succeeds at once, running the caller's onSuccess. */
const succeeding = (value?: unknown) =>
  vi.fn((_: unknown, opts?: { onSuccess?: (v?: unknown) => void }) => opts?.onSuccess?.(value));

const SKILL = "skills/coffer-guide/SKILL.md";
const NOTE = "knowledge/team-runbooks/retries.md";
const SECRET = "secret/sync.PUSH_TOKEN.enc";
const MERGEABLE = { agent_mergeable: true } as const;

let answer: ReturnType<typeof vi.fn>;
let editor: ReturnType<typeof vi.fn>;
let proceed: ReturnType<typeof vi.fn>;
let discard: ReturnType<typeof vi.fn>;
let handoff: ReturnType<typeof vi.fn>;
let chooseJoin: ReturnType<typeof vi.fn>;

type Versions = Partial<ReturnType<typeof makeVersions>>;

function versions(over: Versions = {}) {
  mocked(hooks.useFileVersions).mockImplementation((path: string) => ({
    data: makeVersions(path, over),
    isLoading: false,
    error: null,
  }));
}

function seed(round: StoppedRound, over: Versions = {}) {
  mocked(hooks.useSyncStop).mockReturnValue({ data: { stopped: true, round }, isLoading: false });
  versions(over);
}

function seedJoin(files: ConflictFile[], over: Versions = {}) {
  mocked(hooks.useJoinChoices).mockReturnValue({ data: { files }, isLoading: false });
  versions(over);
}

function show(path?: string, mode?: "join") {
  const params = new URLSearchParams();
  if (mode) params.set("mode", mode);
  if (path) params.set("path", path);
  return render(
    <MemoryRouter initialEntries={[`/sync/conflicts?${params}`]}>
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
  discard = succeeding();
  handoff = vi.fn(() => Promise.resolve("the prompt"));
  chooseJoin = succeeding({ files: [] });
  mocked(hooks.useSyncStop).mockReturnValue({ data: undefined, isLoading: false });
  mocked(hooks.useJoinChoices).mockReturnValue({ data: undefined, isLoading: false });
  mocked(hooks.useAnswerFile).mockReturnValue(idleMutation({ mutate: answer }));
  mocked(hooks.useOpenInEditor).mockReturnValue(idleMutation({ mutate: editor }));
  mocked(hooks.useDiscardCopy).mockReturnValue(idleMutation({ mutate: discard }));
  mocked(hooks.useHandoffRequest).mockReturnValue(handoff);
  mocked(hooks.useContinueRound).mockReturnValue(idleMutation({ mutate: proceed }));
  mocked(hooks.useChooseJoin).mockReturnValue(idleMutation({ mutate: chooseJoin }));
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
    expect(discard).toHaveBeenCalledWith(SKILL, expect.anything());
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
    seed(makeStopped([makeConflict(SECRET, { area: "secret", secret: true })]));
    show();
    const pane = within(screen.getByTestId(`conflict-pane-${SECRET}`));
    expect(pane.getAllByRole("radio")).toHaveLength(2);
    expect(pane.queryByRole("button", { name: /open in editor/i })).toBeNull();
    expect(pane.queryByRole("button", { name: "Hand off to Claude Code" })).toBeNull();
    expect(pane.getByTestId("sync-conflict-secret")).toHaveTextContent(
      /encrypted secret: its contents are not shown/,
    );

    // Even with theirs picked, no diff of its contents is fetched or shown.
    seed(makeStopped([makeConflict(SECRET, { area: "secret", secret: true, answer: "theirs" })]));
    show();
    expect(screen.queryByTestId("sync-conflict-diff")).toBeNull();
    expect(hooks.useFileVersions).not.toHaveBeenCalled();
  });

  test("a mergeable file offers Hand off to Claude Code for this file only, with the agent named", () => {
    seed(makeStopped([makeConflict(SKILL, MERGEABLE), makeConflict(NOTE)]));
    const { unmount } = show(SKILL);
    fireEvent.click(
      within(screen.getByTestId(`conflict-pane-${SKILL}`)).getByRole("button", {
        name: "Hand off to Claude Code",
      }),
    );
    expect(handoff).toHaveBeenCalledWith({ paths: [SKILL], agent: "Claude Code" });
    unmount();

    // A decision (a file changed on one side, deleted on the other) is not a merge.
    show(NOTE);
    expect(screen.queryByRole("button", { name: "Hand off to Claude Code" })).toBeNull();
  });

  acceptance("vault-sync", "an agent's merge is shown to be checked and marked resolved", () => {
    const handed = makeConflict(SKILL, {
      ...MERGEABLE,
      agent_state: "handed_off",
      agent_name: "Claude Code",
      agent_handed_at: "2026-09-13T09:10:00Z",
    });
    seed(makeStopped([handed, makeConflict(NOTE)]));
    const { unmount } = show(SKILL);
    expect(files().getByTestId(`conflict-file-${SKILL}`)).toHaveTextContent("Handed to an agent");
    expect(screen.getByTestId("sync-conflict-handed")).toHaveTextContent(/Handed to Claude Code/);
    unmount();

    const merged = {
      ...handed,
      agent_state: "merged_by_agent",
      agent_merged_at: "2026-09-13T09:41:00Z",
    } as const;
    seed(makeStopped([merged, makeConflict(NOTE)]), {
      merged: "merged\n",
      merged_diff: "@@ -1,1 +1,2 @@\n-mine\n+mine\n+and theirs\n",
    });
    show(SKILL);
    expect(files().getByTestId(`conflict-file-${SKILL}`)).toHaveTextContent(
      "Merged by an agent · check it",
    );
    const card = within(screen.getByTestId("sync-conflict-merged"));
    expect(card.getByText(/Claude Code merged both versions at/)).toBeInTheDocument();
    // The merge is shown against this Mac's version, and is no answer yet.
    expect(screen.getByTestId("sync-conflict-diff")).toHaveTextContent("and theirs");
    expect(screen.queryByRole("radio")).toBeNull();
    expect(card.queryByRole("link", { name: "Open conversation" })).toBeNull();
    expect(screen.getByRole("button", { name: "Continue round" })).toBeDisabled();

    fireEvent.click(card.getByRole("button", { name: "Mark resolved" }));
    expect(answer).toHaveBeenCalledWith({ path: SKILL, answer: "edited" });
    fireEvent.click(card.getByRole("button", { name: "Back to two choices" }));
    expect(discard).toHaveBeenCalledWith(SKILL, expect.anything());
  });

  acceptance("vault-sync", "a join's differing files are handed to an agent too", () => {
    seedJoin([
      makeConflict(NOTE, { reason: "join_differs", ...MERGEABLE }),
      makeConflict(SKILL, { reason: "join_differs", ...MERGEABLE }),
    ]);
    show(NOTE, "join");
    expect(screen.getByRole("heading", { name: "Choose versions" })).toBeInTheDocument();
    expect(hooks.useOpenInEditor).toHaveBeenCalledWith({ join: true });
    expect(hooks.useHandoffRequest).toHaveBeenCalledWith({ join: true });

    fireEvent.click(screen.getByRole("button", { name: "Hand off to Claude Code" }));
    expect(handoff).toHaveBeenCalledWith({ paths: [NOTE], agent: "Claude Code" });

    // Choices are staged; Apply choices sends them together, and nothing else is sent.
    const apply = screen.getByRole("button", { name: "Apply choices" });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "Take Mac mini’s" }));
    expect(answer).not.toHaveBeenCalled();
    expect(screen.getByTestId("sync-conflicts-progress")).toHaveTextContent("1 of 2 files chosen");
    fireEvent.click(screen.getByRole("button", { name: "Apply choices" }));
    expect(chooseJoin).toHaveBeenCalledWith([{ path: NOTE, answer: "theirs" }], expect.anything());
  });

  test("a join's Mark resolved is sent at once and refused in place", () => {
    seedJoin([makeConflict(NOTE, { reason: "join_differs", ...MERGEABLE })], {
      edited: "<<<<<<< this Mac\n",
    });
    mocked(hooks.useChooseJoin).mockReturnValue(
      idleMutation({
        mutate: chooseJoin,
        error: new ApiError(
          "SYNC_CONFLICT_MARKERS_LEFT",
          `Line 2 of ${NOTE} still has conflict markers. Remove them, save, then mark it resolved.`,
        ),
      }),
    );
    show(NOTE, "join");
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    fireEvent.click(screen.getByRole("button", { name: "Mark resolved" }));
    expect(chooseJoin).toHaveBeenCalledWith([{ path: NOTE, answer: "edited" }], expect.anything());
    expect(screen.getByRole("alert")).toHaveTextContent(/Line 2 .* still has conflict markers/);
  });
});
