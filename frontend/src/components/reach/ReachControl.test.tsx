// frontend/src/components/reach/ReachControl.test.tsx
//
// The shared reach control on its own: what the one button says, and the rule
// that EVERY change is handed over at once — each mode switch and each tick —
// with no Done button and nothing deferred to the panel closing.
//
// Two rules are load-bearing. OFF IS A CHOICE, never an inference: it has its
// own endpoint and leaves the scope untouched, so it writes `onDisabled`, and
// Chosen agents is never empty (the last tick stays, nothing saves on a switch
// to it with nothing ticked).
// And the list is dimmed (ticks kept) under every mode but Chosen agents.
//
// A scope stores agent UIDS and a person reads agent NAMES, so the fixtures
// carry both, deliberately unalike.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import "@/i18n";
import { ReachControl } from "./ReachControl";
import type { ReachMode } from "@/lib/reach/reachState";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const agentHooks = await import("@/lib/hooks/useAgents");

const CLAUDE = "u-agent-7f21";
const CODEX = "u-agent-be04";
/** A uid in a stored scope that no registered agent answers to. */
const GHOST = "u-agent-0000";

const AGENTS = [
  { uid: CLAUDE, name: "claude", type: "claude_code" },
  { uid: CODEX, name: "codex", type: "codex" },
];

function seed(agents: { uid: string; name: string; type?: string }[] = AGENTS) {
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
}

const handlers = () => ({ onDisabled: vi.fn(), onEverywhere: vi.fn(), onRestricted: vi.fn() });
const only = (agents: string[] | null): Scope => ({ agents });

const trigger = () => within(screen.getByTestId("scope-control")).getByRole("button");
const openPanel = () => fireEvent.click(trigger());
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });
const closePanel = () =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
const agentRow = (name: string) => within(screen.getByTestId(`scope-agent-${name}`));

function mount(mode: ReachMode, props: Partial<Parameters<typeof ReachControl>[0]> = {}) {
  const h = handlers();
  render(<ReachControl mode={mode} {...h} {...props} />);
  return h;
}

afterEach(() => vi.clearAllMocks());

describe("the button says what the reach is", () => {
  test("there is ONE button", () => {
    seed();
    mount("everywhere");
    expect(within(screen.getByTestId("scope-control")).getAllByRole("button")).toHaveLength(1);
  });

  test("All agents and Off are words", () => {
    seed();
    mount("everywhere");
    expect(trigger()).toHaveTextContent(/^All agents$/);
  });

  test("Off reads Off, even with ticks kept underneath", () => {
    seed();
    mount("disabled", { initialScope: only([CLAUDE]) });
    expect(trigger()).toHaveTextContent(/^Off$/);
  });

  test("a chosen list is badges only — never a count", () => {
    seed();
    mount("restricted", { initialScope: only([CLAUDE, CODEX]) });
    expect(trigger().textContent).toBe("");
    expect(trigger()).toHaveAccessibleName("claude, codex");
    expect(trigger().querySelectorAll("[data-agent-mark]")).toHaveLength(2);
  });
});

describe("the panel", () => {
  test("offers Off / All agents / Chosen agents with their one-line descriptions", () => {
    seed();
    mount("everywhere");
    openPanel();
    const rows = screen.getAllByRole("radio").map((r) => r.closest("div")?.textContent);
    expect(rows).toEqual([
      "OffNo agent can use it; your ticks are kept",
      "All agentsIncluding agents you add later",
      "Chosen agentsOnly the ones ticked below",
    ]);
    expect(choice(/^all agents$/i)).toBeChecked();
  });

  test("drops the machine-local line and has no Done button", () => {
    seed();
    mount("restricted", { initialScope: only([CLAUDE]) });
    openPanel();
    expect(screen.queryByText(/this machine only/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /^done$/i })).toBeNull();
  });

  test("has a Filter agents box that narrows the list", () => {
    seed();
    mount("restricted", { initialScope: only([CLAUDE]) });
    openPanel();
    fireEvent.change(screen.getByRole("textbox", { name: "Filter agents" }), {
      target: { value: "codex" },
    });
    expect(screen.queryByTestId("scope-agent-claude")).toBeNull();
    expect(screen.getByTestId("scope-agent-codex")).toBeInTheDocument();
  });

  test("the list is dimmed and frozen unless Chosen agents, ticks kept", () => {
    seed();
    mount("everywhere", { initialScope: only([CLAUDE]) });
    openPanel();
    const box = agentRow("claude").getByRole("checkbox");
    expect(box).toBeDisabled();
    expect(box).toBeChecked();
    expect(
      screen.getByTestId("scope-agent-axis").querySelector(".opacity-\\[\\.45\\]"),
    ).not.toBeNull();
  });

  test("the footer carries the summary — the only place a count appears", () => {
    seed();
    mount("restricted", { initialScope: only([CLAUDE]) });
    openPanel();
    expect(screen.getByTestId("reach-summary")).toHaveTextContent("1 of 2 agents");
    fireEvent.click(choice(/^off$/i));
    expect(screen.getByTestId("reach-summary")).toHaveTextContent(/^Off$/);
  });

  test("the footer shows the save state", () => {
    seed();
    mount("everywhere", { saveState: "applying" });
    openPanel();
    expect(screen.getByRole("status")).toHaveTextContent("Applying…");
  });

  test("an unknown uid in the stored scope keeps its row, badged", () => {
    seed();
    mount("restricted", { initialScope: only([GHOST]) });
    openPanel();
    expect(agentRow(GHOST).getByRole("checkbox")).toBeChecked();
    expect(agentRow(GHOST).getByText(/not added here/i)).toBeInTheDocument();
  });

  test("the note turns the button amber and shows in the panel", () => {
    seed();
    mount("restricted", { initialScope: only([GHOST]), note: "Inactive here" });
    expect(trigger()).toHaveClass("text-warning");
    openPanel();
    expect(screen.getByText("Inactive here")).toBeInTheDocument();
  });
});

describe("every change is written at once", () => {
  test("Off calls onDisabled immediately and the panel stays open", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/^off$/i));
    expect(h.onDisabled).toHaveBeenCalledOnce();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    expect(choice(/^off$/i)).toBeChecked();
  });

  test("All agents calls onEverywhere immediately", () => {
    seed();
    const h = mount("disabled", { initialScope: only([CLAUDE]) });
    openPanel();
    fireEvent.click(choice(/^all agents$/i));
    expect(h.onEverywhere).toHaveBeenCalledOnce();
  });

  test("re-picking the live mode writes nothing", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/^all agents$/i));
    expect(h.onEverywhere).not.toHaveBeenCalled();
  });

  test("Chosen agents writes the remembered list straight away", () => {
    seed();
    const h = mount("disabled", { initialScope: only([CODEX]) });
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    expect(h.onRestricted).toHaveBeenCalledWith(only([CODEX]), null);
  });

  test("Chosen agents with nothing ticked writes nothing until the first tick", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    expect(choice(/chosen agents/i)).toBeChecked();
    expect(h.onRestricted).not.toHaveBeenCalled();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    expect(h.onRestricted).toHaveBeenCalledWith(only([CLAUDE]), CLAUDE);
  });

  acceptance("web-ui", "the last ticked agent cannot be unticked", () => {
    seed();
    const h = mount("restricted", { initialScope: only([CLAUDE]) });
    openPanel();
    expect(agentRow("claude").getByRole("checkbox")).toBeDisabled();
    expect(screen.getByTestId("scope-keep-one")).toHaveTextContent("Turn it off to reach no agent");
    expect(h.onRestricted).not.toHaveBeenCalled();
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    expect(h.onRestricted).toHaveBeenCalledWith(only([CLAUDE, CODEX]), CODEX);
    expect(screen.queryByTestId("scope-keep-one")).toBeNull();
    expect(agentRow("claude").getByRole("checkbox")).toBeEnabled();
  });

  acceptance("web-ui", "each reach change is saved at once", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    expect(h.onRestricted).toHaveBeenLastCalledWith(only([CLAUDE]), CLAUDE);
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    expect(h.onRestricted).toHaveBeenLastCalledWith(only([CLAUDE, CODEX]), CODEX);
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    expect(h.onRestricted).toHaveBeenLastCalledWith(only([CODEX]), null);
    expect(h.onRestricted).toHaveBeenCalledTimes(3);
  });

  test("a prop refresh while the panel is open does not undo the ticks", () => {
    seed();
    const h = handlers();
    const { rerender } = render(<ReachControl mode="everywhere" {...h} />);
    openPanel();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    rerender(<ReachControl mode="everywhere" {...h} />);
    expect(agentRow("claude").getByRole("checkbox")).toBeChecked();
  });

  test("closing an untouched panel writes nothing, and onClose fires", () => {
    seed();
    const onClose = vi.fn();
    const h = mount("disabled", { onClose });
    openPanel();
    closePanel();
    expect(h.onDisabled).not.toHaveBeenCalled();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onRestricted).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("a failed write shows on the agent's row", () => {
  const failure = (retry = vi.fn()) => ({ uid: CODEX, message: "permission denied", retry });

  acceptance("web-ui", "a failed reach write stays on the agent's row", () => {
    seed();
    const retry = vi.fn();
    const h = mount("restricted", { initialScope: only([CLAUDE, CODEX]), failure: failure(retry) });
    openPanel();
    const row = agentRow("codex");
    expect(row.getByText("Failed")).toBeInTheDocument();
    expect(row.getByText("permission denied")).toBeInTheDocument();
    fireEvent.click(row.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
    fireEvent.click(row.getByRole("button", { name: /untick codex/i }));
    expect(h.onRestricted).toHaveBeenLastCalledWith(only([CLAUDE]), null);
    expect(agentRow("claude").queryByText("Failed")).toBeNull();
  });
});

describe("reach conventions (web-ui)", () => {
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
    expect(label("everywhere")).toBe("All agents");
    expect(label("restricted", only([CLAUDE, CODEX]))).toBe("");
    expect(label("disabled", only([CLAUDE]))).toBe("Off");
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
    expect(choice(/^all agents$/i)).toBeChecked();
    fireEvent.click(choice(/chosen agents/i));
    expect(choice(/chosen agents/i)).toBeChecked();
    expect(within(screen.getByTestId("scope-agent-axis")).getAllByRole("checkbox")).toHaveLength(
      AGENTS.length,
    );
  });

  acceptance("web-ui", "a dismissed reach panel writes nothing", () => {
    seed();
    const h = mount("everywhere");
    openPanel();
    closePanel();
    expect(h.onDisabled).not.toHaveBeenCalled();
    expect(h.onEverywhere).not.toHaveBeenCalled();
    expect(h.onRestricted).not.toHaveBeenCalled();
  });

  acceptance("web-ui", "a reach narrowed to chosen agents shows their badges", () => {
    seed([
      { uid: CLAUDE, name: "Claude Code", type: "claude_code" },
      { uid: CODEX, name: "Codex", type: "codex" },
    ]);
    mount("restricted", { initialScope: only([CLAUDE]) });

    // Badges alone: no count text on the button.
    expect(trigger().textContent).toBe("");
    const marks = trigger().querySelectorAll("[data-agent-mark]");
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveAttribute("data-agent-mark", "claude-spark");

    openPanel();
    const claudeRow = screen.getByTestId("scope-agent-Claude Code");
    expect(claudeRow.querySelector('[data-agent-mark="claude-spark"]')).not.toBeNull();
    const codexRow = screen.getByTestId("scope-agent-Codex");
    expect(codexRow.querySelector('[data-agent-mark="openai-blossom"]')).not.toBeNull();
  });
});
