// frontend/src/components/reach/ReachControl.test.tsx
//
// The shared reach control, tested on its own rather than only through
// ScopeControl — three surfaces mount it (the row, the detail header, the bulk
// bar), and its contract is the same for all of them: what the one button says,
// and that every change is handed over AT ONCE (the bulk bar, whose `apply`
// variant stages and hands over on Apply, aside).
//
// The load-bearing rules: Off is a choice, never an inference (it writes
// `onDisabled`, and an empty pick-list is a different state wearing a
// different label, "No agent"); a failed write is shown in the panel with its
// reason and a Retry, and the view snaps back.
//
// A scope stores agent UIDS and a person reads agent NAMES, so the fixtures
// below carry both, deliberately unalike: a tick writes the uid, the row is
// labelled and found by the name, and a fixture where the two coincided could
// not tell one from the other.
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import i18n from "@/i18n";
import { reachFilterOptions } from "@/lib/reachFilter";
import { ReachFilter } from "./ReachFilter";
import { ReachControl } from "./ReachControl";
import type { ReachMode } from "@/lib/reach/reachState";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const agentHooks = await import("@/lib/hooks/useAgents");

/** The agents registered on this machine: the uid a scope stores, beside the
 *  name the pick-list prints. */
const CLAUDE = "u-agent-7f21";
const CODEX = "u-agent-be04";
/** A uid in a stored scope that no registered agent answers to. */
const GHOST = "u-agent-0000";

const AGENTS = [
  { uid: CLAUDE, name: "claude" },
  { uid: CODEX, name: "codex" },
];

function seed(agents: { uid: string; name: string }[] = AGENTS) {
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
}

const handlers = () => ({
  onDisabled: vi.fn(),
  onEverywhere: vi.fn(),
  onRestricted: vi.fn(),
});

/** Let a queued write settle. */
const settle = () => act(async () => {});

/** A scope, as the wire spells it: agent UIDS, never names. */
const only = (agents: string[] | null): Scope => ({ agents });

/** The one button: there is exactly one, and its text is the state. */
const trigger = (testId = "scope-control") =>
  within(screen.getByTestId(testId)).getByRole("button");
const openPanel = () => fireEvent.click(trigger());
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });
/** One agent's row, found the way the DOM labels it — by the NAME the user
 *  reads, even though ticking it writes the uid. */
const agentRow = (name: string) => within(screen.getByTestId(`scope-agent-${name}`));

function mount(mode: ReachMode | null, props: Partial<Parameters<typeof ReachControl>[0]> = {}) {
  const h = handlers();
  render(<ReachControl mode={mode} {...h} {...props} />);
  return h;
}

afterEach(() => vi.clearAllMocks());

describe("the button says what the reach is", () => {
  test("there is ONE button, not a row of segments", () => {
    seed();
    mount("everywhere");
    expect(within(screen.getByTestId("scope-control")).getAllByRole("button")).toHaveLength(1);
  });

  test("everywhere reads as All agents", () => {
    seed();
    mount("everywhere");
    expect(trigger()).toHaveTextContent(/^all agents$/i);
  });

  test("chosen agents show only their badges, no count in words", () => {
    seed();
    mount("restricted", { initialScope: only([CLAUDE, CODEX]) });
    // The count survives for assistive tech only.
    expect(trigger().querySelector(".sr-only")).toHaveTextContent("2 agents");
    const visibleText = [...trigger().querySelectorAll(":scope > span:not(.sr-only)")].filter(
      (el) => el.getAttribute("aria-hidden") !== "true",
    );
    expect(visibleText).toHaveLength(0);
  });

  test("off reads as Off", () => {
    seed();
    mount("disabled", { initialScope: only([CLAUDE]) });
    expect(trigger()).toHaveTextContent(/^off$/i);
  });

  test("an empty pick-list is NOT 'off' — it reads No agent", () => {
    seed();
    mount("restricted", { initialScope: only([]) });
    expect(trigger()).toHaveTextContent(/^no agent$/i);
  });

  test("a scope spelling 'every agent' the long way still reads as All agents", () => {
    seed();
    mount("restricted", { initialScope: only(null) });
    expect(trigger()).toHaveTextContent(/^all agents$/i);
  });

  test("`mode: null` names no state — it names the action instead", () => {
    seed();
    mount(null);
    expect(trigger()).toHaveTextContent(/set reach/i);
  });

  test("a bulk write in flight makes the button inert", () => {
    seed();
    mount("everywhere", { busy: true });
    expect(trigger()).toBeDisabled();
  });
});

describe("the panel", () => {
  test("is headed Available to, with the resource's name small under it", () => {
    seed();
    mount("everywhere", { resourceName: "Team bot" });
    openPanel();
    expect(screen.getByText("Available to")).toBeInTheDocument();
    expect(screen.getByText("Team bot")).toBeInTheDocument();
  });

  test("offers Off, All agents and Chosen agents with the live one chosen", () => {
    seed();
    mount("everywhere");
    openPanel();
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.closest("label")?.textContent)).toEqual([
      "Off",
      "All agents",
      "Chosen agents",
    ]);
    expect(choice(/all agents/i)).toBeChecked();
    expect(screen.getByText("No agent can use it; your ticks are kept")).toBeInTheDocument();
    expect(screen.getByText("Including agents you add later")).toBeInTheDocument();
    expect(screen.getByText("Only the ones ticked below")).toBeInTheDocument();
  });

  test("a mixed selection opens with nothing chosen", () => {
    seed();
    mount(null, { apply: true });
    openPanel();
    expect(
      screen.getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked),
    ).toHaveLength(0);
  });

  test("no longer carries the machine-local note", () => {
    seed();
    mount("everywhere");
    openPanel();
    expect(screen.queryByText(/this machine only/i)).not.toBeInTheDocument();
  });

  test("the list is dimmed and inert unless the mode is Chosen agents, ticks kept", () => {
    seed();
    mount("disabled", { initialScope: only([CODEX]) });
    openPanel();
    expect(screen.getByTestId("scope-agent-list")).toHaveClass("opacity-45");
    expect(agentRow("codex").getByRole("checkbox")).toBeChecked();
    expect(agentRow("codex").getByRole("checkbox")).toBeDisabled();
    expect(agentRow("claude").getByRole("checkbox")).toBeDisabled();
  });

  test("the list is live under Chosen agents", () => {
    seed();
    mount("restricted", { initialScope: only([CODEX]) });
    openPanel();
    expect(screen.getByTestId("scope-agent-list")).not.toHaveClass("opacity-45");
    expect(agentRow("claude").getByRole("checkbox")).toBeEnabled();
  });

  test("Filter agents narrows the rows by name and keeps hidden ticks", () => {
    seed();
    mount("restricted", { initialScope: only([CLAUDE]) });
    openPanel();
    fireEvent.change(screen.getByRole("textbox", { name: "Filter agents" }), {
      target: { value: "cod" },
    });
    expect(screen.queryByTestId("scope-agent-claude")).not.toBeInTheDocument();
    expect(screen.getByTestId("scope-agent-codex")).toBeInTheDocument();
  });

  test("the pick-list is what is registered, never free text", () => {
    seed();
    mount("restricted", { initialScope: only([]) });
    openPanel();
    expect(within(screen.getByTestId("scope-agent-axis")).getAllByRole("checkbox")).toHaveLength(2);
  });

  test("a seeded uid nothing registered answers to still renders, badged", () => {
    seed();
    mount("restricted", { initialScope: only([GHOST, CLAUDE]) });
    openPanel();
    expect(within(screen.getByTestId(`scope-agent-${GHOST}`)).getByRole("checkbox")).toBeChecked();
    expect(screen.getByText(/not added here/i)).toBeInTheDocument();
  });

  test("with no agent registered and none seeded, the list says so", () => {
    seed([]);
    mount("everywhere");
    openPanel();
    expect(screen.getByText(/no agents added yet/i)).toBeInTheDocument();
  });

  test("the consumer's `note` is shown in the panel, and colours the button", () => {
    seed();
    mount("restricted", { initialScope: only([GHOST]), note: "Inactive here" });
    expect(trigger()).toHaveClass("text-warning");
    openPanel();
    expect(screen.getByText("Inactive here")).toBeInTheDocument();
  });

  test("the footer summarises the reach on the left", () => {
    seed();
    mount("restricted", { initialScope: only([CLAUDE]) });
    openPanel();
    expect(screen.getByTestId("reach-summary")).toHaveTextContent("1 of 2 agents");
    fireEvent.click(choice(/all agents/i));
    expect(screen.getByTestId("reach-summary")).toHaveTextContent("All agents");
    fireEvent.click(choice(/^off$/i));
    expect(screen.getByTestId("reach-summary")).toHaveTextContent("Off");
  });
});

describe("every change saves at once", () => {
  test("opening and closing the panel writes nothing", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(h.onDisabled).not.toHaveBeenCalled();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onRestricted).not.toHaveBeenCalled();
  });

  test("Off writes onDisabled and nothing else, and the panel stays open", async () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/^off$/i));
    await settle();
    expect(h.onDisabled).toHaveBeenCalledOnce();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onRestricted).not.toHaveBeenCalled();
    expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    expect(screen.getByTestId("reach-save-state")).toHaveTextContent("✓ Saved");
  });

  test("All agents writes onEverywhere", async () => {
    seed();
    const h = mount("disabled", { initialScope: only([CLAUDE]) });
    openPanel();
    fireEvent.click(choice(/all agents/i));
    await settle();
    expect(h.onEverywhere).toHaveBeenCalledOnce();
  });

  test("re-picking the live mode writes nothing", async () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/all agents/i));
    await settle();
    expect(h.onEverywhere).not.toHaveBeenCalled();
  });

  test("switching to Chosen agents hands back the stored list (Off keeps ticks)", async () => {
    seed();
    const h = mount("disabled", { initialScope: only([CODEX]) });
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    await settle();
    expect(h.onRestricted).toHaveBeenCalledWith(only([CODEX]));
  });

  test("switching to Chosen agents from All agents writes the empty list — never {agents: null}", async () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    await settle();
    expect(h.onRestricted).toHaveBeenCalledWith(only([]));
    expect(trigger()).toHaveTextContent(/^no agent$/i);
    expect(screen.getByTestId("reach-summary")).toHaveTextContent("0 of 2 agents");
  });

  test("a switch to All agents and back brings the earlier ticks back", async () => {
    seed();
    const h = mount("restricted", { initialScope: only([CLAUDE]) });
    openPanel();
    fireEvent.click(choice(/all agents/i));
    await settle();
    fireEvent.click(choice(/chosen agents/i));
    await settle();
    expect(h.onRestricted).toHaveBeenLastCalledWith(only([CLAUDE]));
  });

  test("each tick writes the whole list at once, as uids", async () => {
    seed();
    const h = mount("restricted", { initialScope: only([]) });
    openPanel();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    await settle();
    expect(h.onRestricted).toHaveBeenCalledTimes(2);
    expect(h.onRestricted).toHaveBeenNthCalledWith(1, only([CLAUDE]));
    expect(h.onRestricted).toHaveBeenNthCalledWith(2, only([CLAUDE, CODEX]));
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    await settle();
    expect(h.onRestricted).toHaveBeenLastCalledWith(only([CODEX]));
  });

  test("ticking preserves the unresolved uids already seeded", async () => {
    seed();
    const h = mount("restricted", { initialScope: only([GHOST]) });
    openPanel();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    await settle();
    expect(h.onRestricted).toHaveBeenCalledWith(only([GHOST, CLAUDE]));
  });

  test("the footer says Saving… while the write is in flight", async () => {
    seed();
    let release: () => void = () => {};
    const h = handlers();
    h.onDisabled.mockReturnValue(new Promise<void>((r) => (release = r)));
    render(<ReachControl mode="everywhere" {...h} />);
    openPanel();
    fireEvent.click(choice(/^off$/i));
    expect(screen.getByTestId("reach-save-state")).toHaveTextContent("Saving…");
    await act(async () => release());
    expect(screen.getByTestId("reach-save-state")).toHaveTextContent("✓ Saved");
  });

  test("a failed tick shows Failed, the reason and a Retry on its row; the tick snaps back", async () => {
    seed();
    const h = handlers();
    h.onRestricted.mockRejectedValueOnce(new Error("disk full"));
    render(<ReachControl mode="restricted" initialScope={only([])} {...h} />);
    openPanel();
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    await settle();
    const failed = screen.getByTestId("scope-agent-failed");
    expect(failed).toHaveTextContent("Failed — disk full");
    expect(agentRow("codex").getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByTestId("reach-save-state")).toHaveTextContent("Couldn't save");

    fireEvent.click(within(failed).getByRole("button", { name: "Retry" }));
    await settle();
    expect(h.onRestricted).toHaveBeenCalledTimes(2);
    expect(h.onRestricted).toHaveBeenLastCalledWith(only([CODEX]));
    expect(screen.queryByTestId("scope-agent-failed")).not.toBeInTheDocument();
    expect(screen.getByTestId("reach-save-state")).toHaveTextContent("✓ Saved");
  });

  test("a failed mode switch is shown under the modes with a Retry", async () => {
    seed();
    const h = handlers();
    h.onDisabled.mockRejectedValueOnce(new Error("nope"));
    render(<ReachControl mode="everywhere" {...h} />);
    openPanel();
    fireEvent.click(choice(/^off$/i));
    await settle();
    expect(screen.getByTestId("scope-mode-failed")).toHaveTextContent("Failed — nope");
    expect(choice(/all agents/i)).toBeChecked();
    fireEvent.click(
      within(screen.getByTestId("scope-mode-failed")).getByRole("button", { name: "Retry" }),
    );
    await settle();
    expect(h.onDisabled).toHaveBeenCalledTimes(2);
  });
});

describe("the bulk (apply) variant stages, then writes once on Apply", () => {
  test("nothing is written until Apply, and the panel closes after", async () => {
    seed();
    const h = mount(null, { apply: true });
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    await settle();
    expect(h.onRestricted).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await settle();
    expect(h.onRestricted).toHaveBeenCalledOnce();
    expect(h.onRestricted).toHaveBeenCalledWith(only([CLAUDE]));
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  test("Apply is disabled until a mode is chosen", () => {
    seed();
    mount(null, { apply: true });
    openPanel();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  test("a rejected Apply keeps the panel open with the reason and a Retry", async () => {
    seed();
    const h = handlers();
    h.onDisabled.mockRejectedValueOnce(new Error("1 succeeded, 1 failed"));
    render(<ReachControl mode={null} apply {...h} />);
    openPanel();
    fireEvent.click(choice(/^off$/i));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await settle();
    expect(screen.getByTestId("scope-mode-failed")).toHaveTextContent("1 succeeded, 1 failed");
    fireEvent.click(
      within(screen.getByTestId("scope-mode-failed")).getByRole("button", { name: "Retry" }),
    );
    await settle();
    expect(h.onDisabled).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  test("agents ticked on only some rows are drawn as a dash", () => {
    seed();
    mount(null, { apply: true, partial: [CODEX] });
    openPanel();
    expect((agentRow("codex").getByRole("checkbox") as HTMLInputElement).indeterminate).toBe(true);
    expect((agentRow("claude").getByRole("checkbox") as HTMLInputElement).indeterminate).toBe(
      false,
    );
  });
});

describe("reach conventions (web-ui)", () => {
  /** Mount one control, read its button, unmount — so four can be compared. */
  function label(mode: ReachMode, scope?: Scope): string {
    const { unmount } = render(<ReachControl mode={mode} initialScope={scope} {...handlers()} />);
    const buttons = within(screen.getByTestId("scope-control")).getAllByRole("button");
    expect(buttons).toHaveLength(1);
    const text = buttons[0].textContent ?? "";
    unmount();
    return text;
  }

  acceptance("web-ui", "the reach button states the reach it holds", () => {
    seed();
    expect(label("everywhere")).toMatch(/^all agents$/i);
    // Chosen agents are drawn as badges; the count is screen-reader text only.
    expect(label("restricted", only([CLAUDE, CODEX]))).toMatch(/^2 agents$/i);
    expect(label("restricted", only([]))).toMatch(/^no agent$/i);
    expect(label("disabled", only([CLAUDE]))).toMatch(/^off$/i);
  });

  acceptance("web-ui", "the reach panel offers the reach states as one choice", () => {
    seed();
    render(<ReachControl mode="everywhere" {...handlers()} />);
    openPanel();
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.closest("label")?.textContent)).toEqual([
      "Off",
      "All agents",
      "Chosen agents",
    ]);
    expect(radios.filter((r) => (r as HTMLInputElement).checked)).toHaveLength(1);
    expect(choice(/all agents/i)).toBeChecked();
    // AND choosing Chosen agents makes the list of agents ticks live.
    const axis = screen.getByTestId("scope-agent-axis");
    expect(within(axis).getAllByRole("checkbox")[0]).toBeDisabled();
    fireEvent.click(choice(/chosen agents/i));
    expect(choice(/chosen agents/i)).toBeChecked();
    expect(within(axis).getAllByRole("checkbox")).toHaveLength(AGENTS.length);
    expect(within(axis).getAllByRole("checkbox")[0]).toBeEnabled();
  });

  acceptance(
    "web-ui",
    "the reach filter offers the panel's states under the reach name",
    async () => {
      seed();
      render(<ReachControl mode="everywhere" {...handlers()} />);
      openPanel();
      const panelLabels = screen.getAllByRole("radio").map((r) => r.closest("label")?.textContent);

      const t = i18n.t.bind(i18n);
      const options = reachFilterOptions(t);
      expect(options.map((o) => o.value)).toEqual(["disabled", "everywhere", "restricted"]);
      expect(options.map((o) => o.label)).toEqual(panelLabels);
      expect(options.map((o) => o.label)).toEqual(["Off", "All agents", "Chosen agents"]);

      // The control a list mounts is a Reach pill offering those states (none chosen = All).
      render(<ReachFilter value="all" onChange={() => {}} />);
      fireEvent.click(screen.getByRole("button", { name: "Reach" }));
      const offered = (await screen.findAllByRole("option")).map((o) => o.textContent);
      expect(offered).toEqual(panelLabels);
    },
  );

  acceptance(
    "web-ui",
    "a reach change saves at once and a failure is shown in the panel",
    async () => {
      seed();
      const h = handlers();
      h.onRestricted.mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error("refused"));
      render(<ReachControl mode="restricted" initialScope={only([])} {...h} />);

      openPanel();
      fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
      expect(h.onRestricted).not.toHaveBeenCalled(); // nothing on dismissal

      openPanel();
      fireEvent.click(agentRow("claude").getByRole("checkbox"));
      fireEvent.click(agentRow("codex").getByRole("checkbox"));
      await settle();
      expect(h.onRestricted).toHaveBeenNthCalledWith(1, only([CLAUDE]));
      expect(h.onRestricted).toHaveBeenNthCalledWith(2, only([CLAUDE, CODEX]));
      expect(
        within(screen.getByTestId("scope-agent-failed")).getByText(/refused/),
      ).toBeInTheDocument();
      expect(
        within(screen.getByTestId("scope-agent-failed")).getByRole("button", { name: "Retry" }),
      ).toBeInTheDocument();
    },
  );

  acceptance("web-ui", "a reach narrowed to chosen agents shows their badges", () => {
    seed([
      { uid: CLAUDE, name: "Claude Code", type: "claude_code" },
      { uid: CODEX, name: "Codex", type: "codex" },
    ] as unknown as { uid: string; name: string }[]);
    mount("restricted", { initialScope: only([CLAUDE]) });

    // The chosen agent's badge is the button's whole visible content; the count
    // stays as its accessible name.
    expect(trigger()).toHaveAccessibleName("1 agent");
    const marks = trigger().querySelectorAll("[data-agent-mark]");
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveAttribute("data-agent-mark", "claude-spark");

    // The panel lists every agent by its badge and its name.
    openPanel();
    const claudeRow = screen.getByTestId("scope-agent-Claude Code");
    expect(claudeRow.querySelector('[data-agent-mark="claude-spark"]')).not.toBeNull();
    expect(within(claudeRow).getByText("Claude Code")).toBeInTheDocument();
    const codexRow = screen.getByTestId("scope-agent-Codex");
    expect(codexRow.querySelector('[data-agent-mark="openai-blossom"]')).not.toBeNull();
    expect(within(codexRow).getByText("Codex")).toBeInTheDocument();
  });
});
