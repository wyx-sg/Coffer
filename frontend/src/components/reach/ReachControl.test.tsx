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
// The second load-bearing rule is that BOTH axes are here — agents and machines
// — so the bulk bar cannot offer less than a row does, and neither of them can
// grow a machine field the other lacks.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ReachControl, type ReachMode } from "./ReachControl";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));
vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn() }));

const agentHooks = await import("@/lib/hooks/useAgents");
const machineHooks = await import("@/lib/hooks/useMachines");

const LOCAL_ID = "a3f21c9e4b7d2610";
const OTHER_ID = "bb11cc22dd33ee44";

const MACHINES = [
  { machine_id: LOCAL_ID, name: "laptop", is_self: true },
  { machine_id: OTHER_ID, name: "desktop", is_self: false },
];

function seed(
  agents: { name: string }[] = [{ name: "claude" }, { name: "codex" }],
  machines: typeof MACHINES = MACHINES,
) {
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
  vi.mocked(machineHooks.useMachines).mockReturnValue({
    data: { machines },
  } as unknown as ReturnType<typeof machineHooks.useMachines>);
}

const handlers = () => ({
  onDisabled: vi.fn(),
  onEverywhere: vi.fn(),
  onRestricted: vi.fn(),
});

const only = (agents: string[] | null, machines: string[] | null = null): Scope => ({
  agents,
  machines,
});

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

describe("the panel stages both axes, then commits once on close", () => {
  test("opening the panel writes nothing, and starts dormant on the agent axis", () => {
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

  test("the machine axis is a pick-list of the registry, never free text", () => {
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    openList();
    // Unrestricted to start with, so the rows only appear once "every machine"
    // is unticked — and then they are checkboxes, not an input.
    fireEvent.click(screen.getByRole("checkbox", { name: /every machine/i }));
    const row = within(screen.getByTestId(`scope-machine-${OTHER_ID}`));
    expect(row.getByText("desktop")).toBeInTheDocument();
    expect(row.getByRole("checkbox")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("scope-machine-axis")).queryByRole("textbox"),
    ).not.toBeInTheDocument();
  });

  test("both axes travel together in the one commit, machines by derived id", () => {
    seed();
    const h = mount("restricted", { initialScope: only(["claude"]) });
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: /every machine/i }));
    fireEvent.click(within(screen.getByTestId(`scope-machine-${OTHER_ID}`)).getByRole("checkbox"));
    closeList();
    expect(h.onRestricted).toHaveBeenCalledOnce();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["claude"], [OTHER_ID]));
  });

  test("the local machine's row is marked as this machine", () => {
    seed();
    mount("restricted", { initialScope: only(null, [LOCAL_ID]) });
    openList();
    expect(
      within(screen.getByTestId(`scope-machine-${LOCAL_ID}`)).getByText(/this machine/i),
    ).toBeInTheDocument();
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

  test("unticking every-agent commits the empty axis — dormant, not 'unchanged'", () => {
    seed();
    const h = mount("restricted", { initialScope: only(null, [LOCAL_ID]) });
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: /every agent/i }));
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closeList();
    expect(h.onRestricted).toHaveBeenCalledWith(only([], [LOCAL_ID]));
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
    seed([{ name: "claude" }]);
    mount("restricted", { initialScope: only(["ghost"]) });
    openList();
    const row = within(screen.getByTestId("scope-agent-ghost"));
    expect(row.getByText("ghost")).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
  });

  test("a machine id the registry does not hold is kept and badged, never dropped", () => {
    // Dropping it would rewrite the user's scope behind their back, and a
    // machine can legally be named before its descriptor has arrived here.
    seed();
    const h = mount("restricted", { initialScope: only(null, ["deadbeefdeadbeef"]) });
    openList();
    const row = within(screen.getByTestId("scope-machine-deadbeefdeadbeef"));
    expect(row.getByText(/not in the registry/i)).toBeInTheDocument();
    expect(row.getByRole("checkbox")).toBeChecked();
    closeList();
    expect(h.onRestricted).toHaveBeenCalledWith(only(null, ["deadbeefdeadbeef"]));
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

  test("with no machine in the registry, the machine axis says so", () => {
    seed(undefined, []);
    mount("restricted", { initialScope: only(null, []) });
    openList();
    expect(screen.getByText(/no machines yet/i)).toBeInTheDocument();
  });

  test("the consumer's `note` is shown in the panel and on the trigger", () => {
    seed();
    mount("restricted", { initialScope: only(["claude"]), note: "Inactive on this machine" });
    expect(segment(/restricted/i)).toHaveAttribute("title", "Inactive on this machine");
    openList();
    expect(screen.getByText("Inactive on this machine")).toBeInTheDocument();
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
