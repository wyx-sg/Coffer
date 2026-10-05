// frontend/src/pages/sync/SyncJoinChoices.test.tsx
//
// The files a join left differing (6.4.23): the same bordered list as a stopped
// round's conflicts, each row saying when each Mac edited it and that a version
// is still to be chosen, with Choose versions (the Resolve page in join mode)
// and one Hand off to Claude Code for every file an agent may merge. Nothing is answered
// from here.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { ConflictFile } from "@/lib/api/sync";
import { SyncJoinChoices } from "./SyncJoinChoices";
import { makeConflict } from "./syncConflictTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({ useJoinChoices: vi.fn(), useHandoffRequest: vi.fn() }));
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

const differing = (path: string, over: Partial<ConflictFile> = {}): ConflictFile =>
  makeConflict(path, { reason: "join_differs", agent_mergeable: true, ...over });

let handoff: ReturnType<typeof vi.fn>;
const seed = (files: ConflictFile[]) =>
  mocked(hooks.useJoinChoices).mockReturnValue({ data: { files } });
const show = () =>
  render(
    <MemoryRouter>
      <SyncJoinChoices />
    </MemoryRouter>,
  );

beforeEach(() => {
  handoff = vi.fn(() => Promise.resolve("the prompt"));
  mocked(hooks.useHandoffRequest).mockReturnValue(handoff);
  seed([differing("knowledge/a.md"), differing("knowledge/b.md")]);
});
afterEach(() => vi.clearAllMocks());

describe("SyncJoinChoices", () => {
  test("says how many files differ, and lists none of them here", () => {
    show();
    expect(screen.getByText("Differ from this Mac")).toBeInTheDocument();
    expect(
      screen.getByText("2 files are not pushed or replaced until you choose a version."),
    ).toBeInTheDocument();
    expect(screen.queryByText("knowledge/a.md")).not.toBeInTheDocument();
  });

  test("Choose versions opens the Resolve page in join mode", () => {
    show();
    expect(screen.getByRole("link", { name: "Choose versions" })).toHaveAttribute(
      "href",
      "/sync/conflicts?mode=join",
    );
  });

  test("Hand off to Claude Code hands over every file at once, naming the agent", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Hand off to Claude Code" }));
    expect(hooks.useHandoffRequest).toHaveBeenCalledWith({ join: true });
    expect(handoff).toHaveBeenCalledWith({ agent: "Claude Code" });
  });

  test("no file an agent may merge, no Hand off to Claude Code", () => {
    seed([differing("secret/a.enc", { agent_mergeable: false, secret: true })]);
    show();
    expect(screen.queryByRole("button", { name: "Hand off to Claude Code" })).toBeNull();
  });

  test("nothing differing renders nothing", () => {
    seed([]);
    const { container } = show();
    expect(container).toBeEmptyDOMElement();
  });
});
