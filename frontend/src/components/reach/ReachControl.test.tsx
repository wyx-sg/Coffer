// frontend/src/components/reach/ReachControl.test.tsx
//
// The shared reach control, tested on its own rather than only through
// ScopeControl — three surfaces mount it (the row, the detail header, the bulk
// bar), and its contract is the same for all of them: what the one button says,
// and WHEN the staged choice is handed over.
//
// The staging rule is the load-bearing one: nothing may be written while the
// panel is open, and closing it must hand over the choice exactly once. Writing
// sooner refetched the list under the open popover, moving the row it was
// anchored to out from under it.
//
// The second load-bearing rule is that DISABLED IS A CHOICE, never an
// inference. It has its own endpoint, its own audit events and its own hook,
// and it deliberately leaves the scope untouched — so it writes `onDisabled`,
// and an empty pick-list (dormant) is a different state wearing a different
// label.
//
// The third is the machine-local line: reach does not sync, and this panel is
// the only place a user is told so. A user who assumed it synced would set
// reach once and never understand why the other machine ignored it.
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

/** The one button: there is exactly one, and its text is the state. */
const trigger = (testId = "scope-control") =>
  within(screen.getByTestId(testId)).getByRole("button");
const openPanel = () => fireEvent.click(trigger());
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });
/** Dismissing the panel is what commits the staged choice. */
const closePanel = () =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

function mount(mode: ReachMode | null, props: Partial<Parameters<typeof ReachControl>[0]> = {}) {
  const h = handlers();
  render(<ReachControl mode={mode} {...h} {...props} />);
  return h;
}

afterEach(() => vi.clearAllMocks());

describe("the button says what the reach is", () => {
  test("there is ONE button, not a row of segments", () => {
    // Three segments spent three controls on two states — "everywhere" is
    // "restricted with everything ticked" — and still made the reader compare
    // all three to learn which was live.
    seed();
    mount("everywhere");
    expect(within(screen.getByTestId("scope-control")).getAllByRole("button")).toHaveLength(1);
  });

  test("everywhere reads as every agent", () => {
    seed();
    mount("everywhere");
    expect(trigger()).toHaveTextContent(/every agent/i);
  });

  test("a restricted scope is reported as a count of agents", () => {
    seed();
    mount("restricted", { initialScope: only(["claude", "codex"]) });
    expect(trigger()).toHaveTextContent(/2 agents/i);
  });

  test("one agent is counted in the singular", () => {
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    expect(trigger()).toHaveTextContent(/^1 agent/i);
  });

  test("disabled reads as disabled", () => {
    seed();
    mount("disabled", { initialScope: only(["claude"]) });
    expect(trigger()).toHaveTextContent(/disabled/i);
  });

  test("an empty pick-list is NOT 'disabled' — it says no agent is selected", () => {
    // Two different states that a single wrong label would fuse: the user did
    // not switch this off, its list simply names nobody.
    seed();
    mount("restricted", { initialScope: only([]) });
    expect(trigger()).toHaveTextContent(/no agent selected/i);
    expect(trigger()).not.toHaveTextContent(/disabled/i);
  });

  test("a scope spelling 'every agent' the long way still reads as every agent", () => {
    seed();
    mount("restricted", { initialScope: only(null) });
    expect(trigger()).toHaveTextContent(/every agent/i);
  });

  test("`mode: null` names no state — it names the action instead", () => {
    // The bulk bar. A mixed selection has no current reach, so a label claiming
    // one would misreport every row that is in a different state.
    seed();
    mount(null);
    expect(trigger()).toHaveTextContent(/set reach/i);
  });

  test("a kind with no scope reads as enabled or disabled, and nothing else", () => {
    seed();
    mount("everywhere", { supportsScope: false });
    expect(trigger()).toHaveTextContent(/^enabled/i);
    expect(trigger()).not.toHaveTextContent(/agent/i);
  });

  test("a write in flight makes the button inert", () => {
    seed();
    mount("everywhere", { busy: true });
    expect(trigger()).toBeDisabled();
  });
});

describe("the panel offers the states as choices", () => {
  test("all three, with the live one already chosen", () => {
    seed();
    mount("everywhere");
    openPanel();
    expect(choice(/^disabled$/i)).not.toBeChecked();
    expect(choice(/every agent/i)).toBeChecked();
    expect(choice(/only selected agents/i)).not.toBeChecked();
  });

  test("a mixed selection opens with nothing chosen", () => {
    seed();
    mount(null);
    openPanel();
    for (const label of [/^disabled$/i, /every agent/i, /only selected agents/i]) {
      expect(choice(label)).not.toBeChecked();
    }
  });

  test("a kind with no scope offers two choices and no agent list", () => {
    seed();
    const h = mount("everywhere", { supportsScope: false });
    openPanel();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByTestId("scope-agent-axis")).not.toBeInTheDocument();
    fireEvent.click(choice(/^enabled$/i));
    expect(h.onEverywhere).toHaveBeenCalledOnce();
  });

  test("every choice is inert while a write is in flight", () => {
    // The trigger is disabled too, so this only bites on a write started from
    // an already-open panel; the panel must not offer a second one.
    seed();
    mount("everywhere");
    openPanel();
    const before = screen.getAllByRole("radio");
    expect(before.every((r) => !(r as HTMLInputElement).disabled)).toBe(true);
  });
});

describe("disabled is its own choice, never inferred", () => {
  test("choosing it reports the intent and nothing else", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/^disabled$/i));
    expect(h.onDisabled).toHaveBeenCalledOnce();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onRestricted).not.toHaveBeenCalled();
  });

  test("emptying the pick-list writes a scope, NOT a disable", () => {
    // The difference the data model turns on: "I switched this off" keeps the
    // selection and fires the disable endpoint; "I cleared the list to re-pick"
    // is a scope reaching nobody. Fusing them would destroy the first.
    seed();
    const h = mount("restricted", { initialScope: only(["claude"]) });
    openPanel();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    closePanel();
    expect(h.onRestricted).toHaveBeenCalledWith(only([]));
    expect(h.onDisabled).not.toHaveBeenCalled();
  });

  test("the panel names the empty list as dormant, in its own words", () => {
    seed();
    mount("restricted", { initialScope: only([]) });
    openPanel();
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    expect(choice(/^disabled$/i)).not.toBeChecked();
  });

  test("a disabled resource still shows the agent list it will come back to", () => {
    // Disabling leaves the scope untouched so re-enabling restores it; showing
    // the remembered selection is the plainest statement that it survived.
    seed();
    mount("disabled", { initialScope: only(["claude"]) });
    openPanel();
    expect(choice(/^disabled$/i)).toBeChecked();
    expect(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox")).toBeChecked();
    expect(screen.queryByText(/dormant/i)).not.toBeInTheDocument();
  });
});

describe("the panel says reach is machine-local", () => {
  test("the panel states that reach is set on this machine only", () => {
    // The decision it reports — reach does not sync — is invisible everywhere
    // else in the app, so the panel where reach is chosen is the one place a
    // user can learn it without reading a doc. Every state is now chosen here,
    // so no user can set reach without passing this line.
    seed();
    mount("everywhere");
    openPanel();
    const line = screen.getByTestId("reach-machine-local");
    expect(line).toHaveTextContent(/this machine only/i);
    expect(line).toHaveTextContent(/not synced/i);
  });

  test("a kind with no scope gets the line too", () => {
    seed();
    mount("everywhere", { supportsScope: false });
    openPanel();
    expect(screen.getByTestId("reach-machine-local")).toHaveTextContent(/not synced/i);
  });

  test("the button carries it as a tooltip, for a reader who never opens it", () => {
    seed();
    mount("everywhere");
    expect(trigger()).toHaveAttribute("title", expect.stringMatching(/this machine/i));
  });

  test("a dormancy note outranks it on the button", () => {
    // Two things want that one tooltip. The note is about THIS resource and is
    // the more urgent, so it wins; the standing fact is still one click away
    // inside the panel.
    seed();
    mount("restricted", { initialScope: only(["claude"]), note: "Inactive here" });
    expect(trigger()).toHaveAttribute("title", "Inactive here");
  });

  test("it is a quiet line, not one of the amber warnings", () => {
    // Amber is reserved for a scope that currently reaches nobody. A standing
    // fact rendered in the same colour would read as a fault every time.
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    openPanel();
    expect(screen.getByTestId("reach-machine-local").className).toContain("text-muted-foreground");
    expect(screen.getByTestId("reach-machine-local").className).not.toContain("status-warn");
  });
});

describe("the panel stages the choice, then commits once on close", () => {
  test("opening the panel writes nothing", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    expect(h.onRestricted).not.toHaveBeenCalled();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onDisabled).not.toHaveBeenCalled();
  });

  test("ticking agents writes nothing until the panel closes, then once", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/only selected agents/i));
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
    expect(h.onRestricted).not.toHaveBeenCalled();

    closePanel();
    expect(h.onRestricted).toHaveBeenCalledOnce();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["claude", "codex"]));
  });

  test("a whole-value choice closes the panel and writes on the way out, once", () => {
    // It commits as the panel goes, not while it is open: a write under an open
    // popover refetched the list and moved the row it is anchored to.
    seed();
    const h = mount("restricted", { initialScope: only(["claude"]) });
    openPanel();
    fireEvent.click(choice(/every agent/i));
    expect(h.onEverywhere).toHaveBeenCalledOnce();
    expect(h.onRestricted).not.toHaveBeenCalled();
    // The panel is gone, so dismissing afterwards cannot write a second time.
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    closePanel();
    expect(h.onEverywhere).toHaveBeenCalledOnce();
  });

  test("a panel the user only glanced at writes NOTHING", () => {
    // With "Disabled" inside the panel, an untouched close would POST a disable
    // on an already-disabled resource — a real audit event for a glance — and
    // the consumer has no "same value" to dedupe that against.
    seed();
    const h = mount("disabled", { initialScope: only(["claude"]) });
    openPanel();
    closePanel();
    expect(h.onDisabled).not.toHaveBeenCalled();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onRestricted).not.toHaveBeenCalled();
  });

  test("re-picking the state it is already in still reports, leaving 'unchanged' to the consumer", () => {
    // The control cannot know whether the seed IS the stored value (the bulk
    // consumer's seed never is), so a deliberate pick always reports;
    // ScopeControl is the one that drops a write matching what is stored.
    seed();
    const h = mount("restricted", { initialScope: only(["claude"]) });
    openPanel();
    fireEvent.click(choice(/only selected agents/i));
    closePanel();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["claude"]));
  });

  test("the agent axis is a pick-list of what is registered, never free text", () => {
    // A mistyped name would match nothing, which makes the resource dormant
    // silently rather than failing — so the names are never typed.
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    openPanel();
    const row = within(screen.getByTestId("scope-agent-codex"));
    expect(row.getByText("codex")).toBeInTheDocument();
    expect(row.getByRole("checkbox")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("scope-agent-axis")).queryByRole("textbox"),
    ).not.toBeInTheDocument();
  });

  test("ticking an agent under 'every agent' narrows in one click", () => {
    // The rows stay on screen under the other choices rather than hiding until
    // "only selected" is picked: ticking a row IS that pick, so narrowing is
    // one click from where the user already is instead of two in a discovered
    // order.
    seed();
    const h = mount("everywhere");
    openPanel();
    expect(choice(/every agent/i)).toBeChecked();

    fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
    expect(choice(/only selected agents/i)).toBeChecked();
    expect(choice(/every agent/i)).not.toBeChecked();

    closePanel();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["codex"]));
    expect(h.onEverywhere).not.toHaveBeenCalled();
  });

  test("the pick-list opens on `initialScope`", () => {
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    openPanel();
    expect(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox")).toBeChecked();
    expect(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox")).not.toBeChecked();
  });

  test("no seed is what a bulk write opens on — a fresh intent, nothing ticked", () => {
    seed();
    mount(null);
    openPanel();
    expect(
      within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"),
    ).not.toBeChecked();
  });

  test("choosing 'only selected agents' from 'every agent' starts dormant", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/only selected agents/i));
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closePanel();
    expect(h.onRestricted).toHaveBeenCalledWith(only([]));
  });

  test("narrowing a stored 'every agent' hands back a list, never `{agents: null}`", () => {
    // `{agents: null}` IS "every agent", which has its own choice and its own
    // callback. A consumer must never have to normalise one into the other, so
    // `onRestricted` only ever carries a list.
    seed();
    const h = mount("restricted", { initialScope: only(null) });
    expect(trigger()).toHaveTextContent(/every agent/i);
    openPanel();
    expect(choice(/every agent/i)).toBeChecked();
    fireEvent.click(choice(/only selected agents/i));
    closePanel();
    expect(h.onRestricted).toHaveBeenCalledWith(only([]));
  });

  test("a seeded agent that is not registered here still renders, badged", () => {
    // Dropping it would rewrite the user's scope behind their back, and a name
    // can legally be scoped in before that agent is registered here.
    seed([{ name: "claude" }]);
    const h = mount("restricted", { initialScope: only(["ghost"]) });
    openPanel();
    const row = within(screen.getByTestId("scope-agent-ghost"));
    expect(row.getByText("ghost")).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
    expect(row.getByRole("checkbox")).toBeChecked();
    fireEvent.click(choice(/only selected agents/i));
    closePanel();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["ghost"]));
  });

  test("ticking an agent preserves the unregistered names already seeded", () => {
    seed([{ name: "claude" }]);
    const h = mount("restricted", { initialScope: only(["ghost"]) });
    openPanel();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    closePanel();
    expect(h.onRestricted).toHaveBeenCalledWith(only(["ghost", "claude"]));
  });

  test("with no agent registered and none seeded, the agent axis says so", () => {
    seed([]);
    mount(null);
    openPanel();
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });

  test("the consumer's `note` is shown in the panel, and colours the button", () => {
    // One button carrying the whole answer would otherwise read "1 agent" —
    // perfectly healthy-looking — while reaching nobody on this machine.
    seed();
    mount("restricted", { initialScope: only(["claude"]), note: "Inactive here" });
    expect(trigger()).toHaveAttribute("title", "Inactive here");
    expect(trigger().className).toContain("status-warn");
    openPanel();
    expect(screen.getByText("Inactive here")).toBeInTheDocument();
  });

  test("without a note the button is not coloured", () => {
    seed();
    mount("restricted", { initialScope: only(["claude"]) });
    expect(trigger().className).not.toContain("status-warn");
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
