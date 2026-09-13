import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { EffortPicker } from "./EffortPicker";

vi.mock("@/lib/hooks/useAgentModels", () => ({ useAgentModels: vi.fn() }));

import type { AgentModel } from "@/lib/api/agentModels";
import { useAgentModels } from "@/lib/hooks/useAgentModels";

const useAgentModelsMock = useAgentModels as unknown as ReturnType<typeof vi.fn>;

/** The daemon-served catalogue per agent. Codex's models carry reasoning
 * levels in Codex's own order; Claude Code's carry none at all. */
const CATALOGUE: Record<string, AgentModel[]> = {
  claude_code: [
    { id: "opus", label: "Opus 5", description: "", efforts: [], default_effort: null },
    { id: "sonnet", label: "Sonnet 4.8", description: "", efforts: [], default_effort: null },
  ],
  codex: [
    {
      id: "gpt-5-codex",
      label: "",
      description: "",
      efforts: ["low", "medium", "high", "xhigh"],
      default_effort: "xhigh",
    },
    {
      id: "gpt-5",
      label: "",
      description: "",
      efforts: ["low", "medium", "high"],
      default_effort: "medium",
    },
  ],
};

/** Open the Radix Select trigger and return its rendered option labels.
 *
 * jsdom has no PointerEvent, so drive the trigger via the keyboard (Radix opens
 * the listbox on ArrowDown / Enter / Space) rather than a pointer gesture. */
function openAndReadOptions(): string[] {
  const trigger = screen.getByRole("combobox", { name: /reasoning effort/i });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

beforeEach(() => {
  vi.clearAllMocks();
  useAgentModelsMock.mockImplementation((agentKey: string) => ({
    data: CATALOGUE[agentKey] ?? [],
  }));
});

describe("EffortPicker", () => {
  test("offers the selected model's levels, in the agent's own order", () => {
    render(<EffortPicker agentKey="codex" model="gpt-5" value={null} onCommit={vi.fn()} />);
    // `gpt-5` stops at high — the four-level list belongs to the other model.
    expect(openAndReadOptions().slice(1)).toEqual(["low", "medium", "high"]);
  });

  test("renders nothing for a model that reports no levels", () => {
    // Claude Code must look exactly as it did before this control existed.
    const { container } = render(
      <EffortPicker agentKey="claude_code" model="opus" value={null} onCommit={vi.fn()} />,
    );
    expect(screen.queryByRole("combobox", { name: /reasoning effort/i })).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  test("renders nothing for an agent whose whole catalogue reports none", () => {
    // No model chosen either: the fallback entry must not conjure a control.
    render(<EffortPicker agentKey="claude_code" model={null} value={null} onCommit={vi.fn()} />);
    expect(screen.queryByRole("combobox", { name: /reasoning effort/i })).toBeNull();
  });

  test("with no model chosen, falls back to the head of the catalogue", () => {
    // The agent runs a default it never names; the first entry stands in for it.
    render(<EffortPicker agentKey="codex" model={null} value={null} onCommit={vi.fn()} />);
    expect(openAndReadOptions().slice(1)).toEqual(["low", "medium", "high", "xhigh"]);
  });

  test("picking a level commits it", () => {
    const onCommit = vi.fn();
    render(<EffortPicker agentKey="codex" model="gpt-5-codex" value={null} onCommit={onCommit} />);
    openAndReadOptions();
    fireEvent.click(screen.getByRole("option", { name: "high" }));
    expect(onCommit).toHaveBeenCalledWith("high");
  });

  test("the inherit sentinel names the agent's own level and clears the override", () => {
    const onCommit = vi.fn();
    render(<EffortPicker agentKey="codex" model="gpt-5-codex" value="low" onCommit={onCommit} />);
    const options = openAndReadOptions();
    // The sentinel row is "<label><the level the agent would pick>".
    expect(options[0]).toBe("Agent defaultxhigh");
    fireEvent.click(screen.getByRole("option", { name: /^Agent default/ }));
    expect(onCommit).toHaveBeenCalledWith(null);
  });

  test("a stored level the agent no longer offers stays selectable", () => {
    // The trigger must never misreport what the conversation actually runs at.
    render(<EffortPicker agentKey="codex" model="gpt-5" value="xhigh" onCommit={vi.fn()} />);
    const trigger = screen.getByRole("combobox", { name: /reasoning effort/i });
    expect(trigger).toHaveTextContent("xhigh");
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toContain("xhigh");
  });

  test("is disabled with the rest of the bar", () => {
    render(
      <EffortPicker agentKey="codex" model="gpt-5" value={null} onCommit={vi.fn()} disabled />,
    );
    expect(screen.getByRole("combobox", { name: /reasoning effort/i })).toBeDisabled();
  });
});
