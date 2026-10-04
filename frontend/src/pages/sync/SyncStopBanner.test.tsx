// frontend/src/pages/sync/SyncStopBanner.test.tsx
//
// The danger banner of a round stopped on conflicts (6.4.05): Resolve conflicts
// as a secondary button, one Hand off to Claude Code for every conflict, and × as Ignore —
// the same item as on Overview, found in the attention list by its reason.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { SyncStopBanner } from "./SyncStopBanner";
import { makeConflict, makeStopped } from "./syncConflictTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({ useSyncStop: vi.fn(), useHandoffRequest: vi.fn() }));
vi.mock("./useSyncIgnore", () => ({
  STOP_REASON: { conflicts: "sync_conflicts", held: "sync_deletions_held" },
  useSyncIgnore: vi.fn(),
}));
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
const { useSyncIgnore } = await import("./useSyncIgnore");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

let handoff: ReturnType<typeof vi.fn>;
let ignore: ReturnType<typeof vi.fn>;

function seed(
  files = [makeConflict("skills/a/SKILL.md", { agent_mergeable: true })],
  ignored = false,
) {
  mocked(hooks.useSyncStop).mockReturnValue({
    data: { stopped: true, round: makeStopped(files) },
  });
  mocked(useSyncIgnore).mockReturnValue({
    isIgnored: () => ignored,
    ignorer: () => ignore,
  });
}

const show = (count = 1) =>
  render(
    <TooltipProvider>
      <MemoryRouter>
        <SyncStopBanner kind="conflicts" count={count} />
      </MemoryRouter>
    </TooltipProvider>,
  );

beforeEach(() => {
  handoff = vi.fn(() => Promise.resolve("the prompt"));
  ignore = vi.fn();
  mocked(hooks.useHandoffRequest).mockReturnValue(handoff);
});
afterEach(() => vi.clearAllMocks());

describe("SyncStopBanner", () => {
  test("says what stopped, leads to Resolve conflicts and hands every conflict over at once", () => {
    seed();
    show(6);
    expect(screen.getByText("This round stopped on 6 conflicts")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resolve conflicts" })).toHaveAttribute(
      "href",
      "/sync/conflicts",
    );
    fireEvent.click(screen.getByRole("button", { name: "Hand off to Claude Code" }));
    // No paths: the daemon hands over every file an agent may merge.
    expect(handoff).toHaveBeenCalledWith({ agent: "Claude Code" });
  });

  test("× is Ignore, and an ignored stop shows no banner", () => {
    seed();
    const { unmount } = show();
    fireEvent.click(screen.getByRole("button", { name: "Ignore" }));
    expect(ignore).toHaveBeenCalled();
    unmount();

    seed(undefined, true);
    const { container } = show();
    expect(container).toBeEmptyDOMElement();
  });

  test("conflicts that are all decisions offer no hand-off", () => {
    seed([makeConflict("skills/a/SKILL.md")]);
    show();
    expect(screen.queryByRole("button", { name: "Hand off to Claude Code" })).toBeNull();
  });
});
