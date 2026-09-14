// frontend/src/components/reach/ReachControl.test.tsx
//
// The shared three-way reach control, tested on its own rather than only
// through ScopeControl — three surfaces mount it (the row, the detail header,
// the bulk bar), and its contract is the same for all of them: which segment
// reads as live, and WHEN the agent list is handed over.
//
// The staging rule is the load-bearing one: ticking agents must write nothing,
// and closing the panel must hand over the whole selection exactly once. Per-tick
// writes refetched the list under the open popover, moving the row it was
// anchored to out from under it.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ReachControl, type ReachMode } from "./ReachControl";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const agentHooks = await import("@/lib/hooks/useAgents");

function seedAgents(agents: { name: string }[] = [{ name: "claude" }, { name: "codex" }]) {
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
}

const handlers = () => ({
  onDisabled: vi.fn(),
  onEveryAgent: vi.fn(),
  onSelectedAgents: vi.fn(),
});

const segment = (label: RegExp) => screen.getByRole("button", { name: label });
const openList = () => fireEvent.click(segment(/selected agents/i));
const closeList = () =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

function mount(mode: ReachMode | null, props: Partial<Parameters<typeof ReachControl>[0]> = {}) {
  const h = handlers();
  render(<ReachControl mode={mode} {...h} {...props} />);
  return h;
}

afterEach(() => vi.clearAllMocks());

describe("the three segments", () => {
  test("all three render, and exactly the named one reads as live", () => {
    seedAgents();
    mount("every");
    expect(segment(/^disabled$/i)).toHaveAttribute("aria-pressed", "false");
    expect(segment(/every agent/i)).toHaveAttribute("aria-pressed", "true");
    expect(segment(/selected agents/i)).toHaveAttribute("aria-pressed", "false");
  });

  test("the disabled segment reports the intent and nothing else", () => {
    seedAgents();
    const h = mount("every");
    fireEvent.click(segment(/^disabled$/i));
    expect(h.onDisabled).toHaveBeenCalledOnce();
    expect(h.onEveryAgent).not.toHaveBeenCalled();
    expect(h.onSelectedAgents).not.toHaveBeenCalled();
  });

  test("the every-agent segment reports the intent and nothing else", () => {
    seedAgents();
    const h = mount("selected", { initialAgents: ["claude"] });
    fireEvent.click(segment(/every agent/i));
    expect(h.onEveryAgent).toHaveBeenCalledOnce();
    expect(h.onSelectedAgents).not.toHaveBeenCalled();
  });

  test("`mode: null` leaves every segment quiet — a bulk write claims no state", () => {
    seedAgents();
    mount(null);
    for (const label of [/^disabled$/i, /every agent/i, /selected agents/i]) {
      expect(segment(label)).toHaveAttribute("aria-pressed", "false");
    }
  });

  test("a write in flight makes every segment inert", () => {
    seedAgents();
    mount("every", { busy: true });
    expect(segment(/^disabled$/i)).toBeDisabled();
    expect(segment(/every agent/i)).toBeDisabled();
    expect(segment(/selected agents/i)).toBeDisabled();
  });

  test("no scope means two segments, and Enabled routes to the every-agent intent", () => {
    seedAgents();
    const h = mount("every", { supportsScope: false });
    expect(screen.queryByRole("button", { name: /every agent/i })).not.toBeInTheDocument();
    expect(segment(/^enabled$/i)).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(segment(/^enabled$/i));
    expect(h.onEveryAgent).toHaveBeenCalledOnce();
  });
});

describe("the agent panel stages, then commits once on close", () => {
  test("opening the panel writes nothing", () => {
    seedAgents();
    const h = mount("every");
    openList();
    expect(h.onSelectedAgents).not.toHaveBeenCalled();
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
  });

  test("ticking agents writes nothing until the panel closes, then once", () => {
    seedAgents();
    const h = mount("every");
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
    expect(h.onSelectedAgents).not.toHaveBeenCalled();

    closeList();
    expect(h.onSelectedAgents).toHaveBeenCalledOnce();
    expect(h.onSelectedAgents).toHaveBeenCalledWith(["claude", "codex"]);
  });

  test("the panel opens on `initialAgents`, and the segment carries their count", () => {
    seedAgents();
    mount("selected", { initialAgents: ["claude"] });
    expect(segment(/selected agents \(1\)/i)).toBeInTheDocument();
    openList();
    expect(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox")).toBeChecked();
    expect(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox")).not.toBeChecked();
  });

  test("an empty seed is what a bulk write opens on — a fresh intent, no count", () => {
    seedAgents();
    mount(null, { initialAgents: [] });
    expect(screen.queryByRole("button", { name: /selected agents \(/i })).not.toBeInTheDocument();
    openList();
    expect(
      within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"),
    ).not.toBeChecked();
  });

  test("unticking down to nothing commits the empty list, not nothing at all", () => {
    seedAgents();
    const h = mount("selected", { initialAgents: ["claude"] });
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    closeList();
    expect(h.onSelectedAgents).toHaveBeenCalledWith([]);
  });

  test("closing an untouched panel still commits, leaving 'unchanged' to the consumer", () => {
    // The control cannot know whether the seed IS the stored value (the bulk
    // consumer's seed never is), so it always reports; ScopeControl is the one
    // that drops a write matching what is stored.
    seedAgents();
    const h = mount("selected", { initialAgents: ["claude"] });
    openList();
    closeList();
    expect(h.onSelectedAgents).toHaveBeenCalledWith(["claude"]);
  });

  test("a seeded name that is not a registered agent still renders, badged", () => {
    seedAgents([{ name: "claude" }]);
    mount("selected", { initialAgents: ["ghost"] });
    openList();
    const row = within(screen.getByTestId("scope-agent-ghost"));
    expect(row.getByText("ghost")).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
  });

  test("ticking an agent preserves the unregistered names already seeded", () => {
    seedAgents([{ name: "claude" }]);
    const h = mount("selected", { initialAgents: ["ghost"] });
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    closeList();
    expect(h.onSelectedAgents).toHaveBeenCalledWith(["ghost", "claude"]);
  });

  test("with no agent registered and none seeded, the panel says so", () => {
    seedAgents([]);
    mount(null);
    openList();
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });

  test("the bulk mount is labelled, so it is distinguishable from a row's", () => {
    seedAgents();
    mount(null, { testId: "bulk-reach-control", ariaLabel: "Reach for the selected" });
    expect(screen.getByTestId("bulk-reach-control")).toHaveAttribute(
      "aria-label",
      "Reach for the selected",
    );
  });
});
