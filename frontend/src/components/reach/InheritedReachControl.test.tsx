// frontend/src/components/reach/InheritedReachControl.test.tsx
//
// The reach of an item inside a group (Foundations-Reach "Inherited reach"):
// Same as the group (default) / All agents / Chosen agents, no Off, every
// change handed over at once.
import { afterEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { InheritedReachControl, type InheritedMode } from "./InheritedReachControl";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));
const agentHooks = await import("@/lib/hooks/useAgents");

const CLAUDE = "u-agent-7f21";
const CODEX = "u-agent-be04";

function mount(mode: InheritedMode, scope: Scope | null = null) {
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: [
      { uid: CLAUDE, name: "claude", type: "claude_code" },
      { uid: CODEX, name: "codex", type: "codex" },
    ],
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
  const h = { onInherit: vi.fn(), onEverywhere: vi.fn(), onRestricted: vi.fn() };
  render(
    <InheritedReachControl
      mode={mode}
      scope={scope}
      inheritedSub="deploy-api gives it to Claude Code and Codex"
      footnote="To stop it for every agent, turn its switch off in the table."
      {...h}
    />,
  );
  return h;
}
const trigger = () => within(screen.getByTestId("inherited-reach-control")).getByRole("button");
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });

afterEach(() => vi.clearAllMocks());

test("the trigger reads Same as the group when inherited", () => {
  mount("inherited");
  expect(trigger()).toHaveTextContent(/^Same as the group$/);
});

test("a chosen override shows badges only", () => {
  mount("restricted", { agents: [CODEX] });
  expect(trigger().textContent).toBe("");
  expect(trigger().querySelectorAll("[data-agent-mark]")).toHaveLength(1);
});

test("offers Same as the group / All agents / Chosen agents — no Off", () => {
  mount("inherited");
  fireEvent.click(trigger());
  expect(screen.getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual([
    "Same as the group",
    "All agents",
    "Chosen agents",
  ]);
  expect(screen.queryByRole("radio", { name: /^off$/i })).toBeNull();
  expect(choice(/same as the group/i)).toBeChecked();
  expect(screen.getByText("deploy-api gives it to Claude Code and Codex")).toBeInTheDocument();
  expect(screen.getByText(/turn its switch off in the table/i)).toBeInTheDocument();
  expect(screen.getByTestId("reach-summary")).toHaveTextContent("Same as the group");
});

test("each change is written at once", () => {
  const h = mount("inherited");
  fireEvent.click(trigger());
  fireEvent.click(choice(/^all agents$/i));
  expect(h.onEverywhere).toHaveBeenCalledOnce();
  fireEvent.click(choice(/chosen agents/i));
  expect(h.onRestricted).toHaveBeenLastCalledWith({ agents: [] }, null);
  fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
  expect(h.onRestricted).toHaveBeenLastCalledWith({ agents: [CODEX] }, CODEX);
  fireEvent.click(choice(/same as the group/i));
  expect(h.onInherit).toHaveBeenCalledOnce();
});

test("the list is dimmed and frozen unless Chosen agents", () => {
  mount("inherited");
  fireEvent.click(trigger());
  expect(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox")).toBeDisabled();
});
