// frontend/src/components/reach/ReachControl.test.tsx
//
// The shared three-way reach control, tested on its own rather than only
// through ScopeControl — three surfaces mount it (the row, the detail header,
// the bulk bar), and its contract is the same for all of them: which segment
// reads as live, and WHEN the staged scope is handed over.
//
// The staging rule is the load-bearing one: ticking entries must write nothing,
// and closing the panel must hand over the whole scope exactly once. Per-tick
// writes refetched the list under the open popover, moving the row it was
// anchored to out from under it.
//
// The second load-bearing rule is the machine-local line: reach does not sync,
// and this panel is the only place a user is told so. A user who assumed it
// synced would set reach once and never understand why the other machine
// ignored it — so the line is asserted here rather than left to a doc.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ReachControl, type ReachMode } from "./ReachControl";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const agentHooks = await import("@/lib/hooks/useAgents");

function seed(agents: { name: string }[] = [{ name: "claude" }, { name: "codex" }]) {
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
}

const handlers = () => ({
  onDisabled: vi.fn(),
  onEverywhere: vi.fn(),
  onRestricted: vi.fn(),
});

const only = (agents: string[] | null): Scope => ({ agents });

const segment = (label: RegExp) => screen.getByRole("button", { name: label });
const openList = () => fireEvent.click(segment(/restricted/i));
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
    seed();
    mount("everywhere");
    expect(segment(/^disabled$/i)).toHaveAttribute("aria-pressed", "false");
    expect(segment(/everywhere/i)).toHaveAttribute("aria-pressed", "true");
    expect(segment(/restricted/i)).toHaveAttribute("aria-pressed", "false");
  });

  test("the disabled segment reports the intent and nothing else", () => {
    seed();
    const h = mount("everywhere");
    fireEvent.click(segment(/^disabled$/i));
    expect(h.onDisabled).toHaveBeenCalledOnce();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onRestricted).not.toHaveBeenCalled();
  });

  test("the everywhere segment reports the intent and nothing else", () => {
    seed();
    const h = mount("restricted", { initialScope: only(["claude"]) });
    fireEvent.click(segment(/everywhere/i));
    expect(h.onEverywhere).toHaveBeenCalledOnce();
    expect(h.onRestricted).not.toHaveBeenCalled();
  });

  test("`mode: null` leaves every segment quiet — a bulk write claims no state", () => {
    seed();
    mount(null);
    for (const label of [/^disabled$/i, /everywhere/i, /restricted/i]) {
      expect(segment(label)).toHaveAttribute("aria-pressed", "false");
    }
  });

  test("a write in flight makes every segment inert", () => {
    seed();
    mount("everywhere", { busy: true });
    expect(segment(/^disabled$/i)).toBeDisabled();
    expect(segment(/everywhere/i)).toBeDisabled();
    expect(segment(/restricted/i)).toBeDisabled();
  });

  test("no scope means two segments, and Enabled routes to the everywhere intent", () => {
    seed();
    const h = mount("everywhere", { supportsScope: false });
    expect(screen.queryByRole("button", { name: /everywhere/i })).not.toBeInTheDocument();
    expect(segment(/^enabled$/i)).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(segment(/^enabled$/i));
    expect(h.onEverywhere).toHaveBeenCalledOnce();
  });
});

describe("the panel says reach is machine-local", () => {
  test("the panel states that reach is set on this machine only", () => {
    // The decision it reports — reach does not sync — is invisible everywhere
    // else in the app, so the panel where reach is chosen is the one place a
    // user can learn it without reading a doc.
    seed();
    mount("everywhere");
    openList();
    const line = screen.getByTestId("reach-machine-local");
    expect(line).toHaveTextContent(/this machine only/i);
    expect(line).toHaveTextContent(/not synced/i);
  });

  test("the whole-value segments carry it too, since they never open the panel", () => {
    // "Disabled" and "Everywhere" commit on the click. A user who only ever
    // uses those two would set reach for the life of this machine without the
    // panel — and its line — ever appearing, so the fact rides the segments as
    // well.
    seed();
    mount("everywhere");
    expect(segment(/^disabled$/i)).toHaveAttribute("title", expect.stringMatching(/this machine/i));
    expect(segment(/^everywhere$/i)).toHaveAttribute("title", expect.stringMatching(/not synced/i));
  });

  test("a dormancy note outranks it on the Restricted segment", () => {
    // Two things want that one tooltip. The note is about THIS resource and is
    // the more urgent, so it wins; the standing fact is still one click away
    // inside the panel.
    seed();
    mount("restricted", { initialScope: only(["claude"]), note: "Inactive here" });
    expect(segment(/^restricted/i)).toHaveAttribute("title", "Inactive here");
  });

  test("it is a quiet line, not one of the amber warnings", () => {
    // Amber is reserved for a scope that currently reaches nobody. A standing
    // fact rendered in the same colour would read as a fault every time.
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    openList();
    expect(screen.getByTestId("reach-machine-local").className).toContain("text-muted-foreground");
    expect(screen.getByTestId("reach-machine-local").className).not.toContain("status-warn");
  });
});

describe("the panel stages the agent list, then commits once on close", () => {
  test("opening the panel writes nothing, and starts dormant", () => {
    seed();
    const h = mount("everywhere");
    openList();
    expect(h.onRestricted).not.toHaveBeenCalled();
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
  });

  test("ticking agents writes nothing until the panel closes, then once", () => {
    seed();
    const h = mount("everywhere");
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
    expect(h.onRestricted).not.toHaveBeenCalled();

    closeList();
    expect(h.onRestricted).toHaveBeenCalledOnce();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["claude", "codex"]));
  });

  test("the agent axis is a pick-list of what is registered, never free text", () => {
    // A mistyped name would match nothing, which makes the resource dormant
    // silently rather than failing — so the names are never typed.
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    openList();
    const row = within(screen.getByTestId("scope-agent-codex"));
    expect(row.getByText("codex")).toBeInTheDocument();
    expect(row.getByRole("checkbox")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("scope-agent-axis")).queryByRole("textbox"),
    ).not.toBeInTheDocument();
  });

  test("an agent can be picked while 'every agent' is still ticked", () => {
    // The rows stay on screen under "every agent" rather than hiding until it
    // is un-ticked: ticking a row IS the un-tick, so narrowing is one click
    // from where the user already is instead of two in a discovered order.
    seed();
    const h = mount("restricted", { initialScope: only(null) });
    openList();

    const every = screen.getByRole("checkbox", { name: /every agent/i });
    expect(every).toBeChecked();
    const row = within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox");
    expect(row).not.toBeChecked();

    fireEvent.click(row);
    expect(screen.getByRole("checkbox", { name: /every agent/i })).not.toBeChecked();

    closeList();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["codex"]));
  });

  test("the panel opens on `initialScope`", () => {
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    openList();
    expect(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox")).toBeChecked();
    expect(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox")).not.toBeChecked();
  });

  test("no seed is what a bulk write opens on — a fresh intent, nothing ticked", () => {
    seed();
    mount(null);
    openList();
    expect(
      within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"),
    ).not.toBeChecked();
  });

  test("unticking every-agent commits the empty list — dormant, not 'unchanged'", () => {
    seed();
    const h = mount("restricted", { initialScope: only(null) });
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: /every agent/i }));
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closeList();
    expect(h.onRestricted).toHaveBeenCalledWith(only([]));
  });

  test("closing an untouched panel still commits, leaving 'unchanged' to the consumer", () => {
    // The control cannot know whether the seed IS the stored value (the bulk
    // consumer's seed never is), so it always reports; ScopeControl is the one
    // that drops a write matching what is stored.
    seed();
    const h = mount("restricted", { initialScope: only(["claude"]) });
    openList();
    closeList();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["claude"]));
  });

  test("a seeded agent that is not registered here still renders, badged", () => {
    // Dropping it would rewrite the user's scope behind their back, and a name
    // can legally be scoped in before that agent is registered here.
    seed([{ name: "claude" }]);
    const h = mount("restricted", { initialScope: only(["ghost"]) });
    openList();
    const row = within(screen.getByTestId("scope-agent-ghost"));
    expect(row.getByText("ghost")).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
    expect(row.getByRole("checkbox")).toBeChecked();
    closeList();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["ghost"]));
  });

  test("ticking an agent preserves the unregistered names already seeded", () => {
    seed([{ name: "claude" }]);
    const h = mount("restricted", { initialScope: only(["ghost"]) });
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    closeList();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["ghost", "claude"]));
  });

  test("with no agent registered and none seeded, the agent axis says so", () => {
    seed([]);
    mount(null);
    openList();
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });

  test("the consumer's `note` is shown in the panel and on the trigger", () => {
    seed();
    mount("restricted", { initialScope: only(["claude"]), note: "Inactive here" });
    expect(segment(/restricted/i)).toHaveAttribute("title", "Inactive here");
    openList();
    expect(screen.getByText("Inactive here")).toBeInTheDocument();
  });

  test("the bulk mount is labelled, so it is distinguishable from a row's", () => {
    seed();
    mount(null, { testId: "bulk-reach-control", ariaLabel: "Reach for the selected" });
    expect(screen.getByTestId("bulk-reach-control")).toHaveAttribute(
      "aria-label",
      "Reach for the selected",
    );
  });
});
