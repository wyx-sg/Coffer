// src/components/agent/AgentOption.test.tsx — agents in selects and filters carry their mark and display name, not the key.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import "@/i18n";
import { acceptance } from "@/test/acceptance";
import { AgentSelect } from "@/components/agents/AgentSelect";
import { user } from "@/components/filters/testUser";
import { FilterPill } from "@/components/filters";
import { AgentReachFilter } from "@/components/reach/AgentReachFilter";

const agents = vi.hoisted(() => ({
  current: [
    { uid: "u-cc", name: "claude-code", display_name: "Claude Code", type: "claude_code" },
    { uid: "u-cx", name: "codex", display_name: "Codex", type: "codex" },
  ] as Array<Record<string, unknown>>,
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: agents.current }) }));

function marks(el: HTMLElement): string[] {
  return [...el.querySelectorAll("[data-agent-mark]")].map(
    (m) => m.getAttribute("data-agent-mark") ?? "",
  );
}

describe("agents in controls", () => {
  acceptance("web-ui", "an agent in a select or filter carries its mark and display name", () => {
    render(<AgentSelect label="Default agent" value="u-cc" onChange={() => {}} />);
    const trigger = screen.getByRole("combobox", { name: "Default agent" });
    expect(trigger).toHaveTextContent("Claude Code");
    expect(trigger).not.toHaveTextContent("claude-code");
    expect(marks(trigger)).toEqual(["claude-spark"]);
  });

  test("the reach filter shows the mark and display name on its trigger", () => {
    render(
      <MemoryRouter>
        <AgentReachFilter
          filter={{ uid: "u-cx", label: null, clear: () => {}, matches: () => true }}
        />
      </MemoryRouter>,
    );
    const trigger = screen.getByRole("combobox", { name: "Reach" });
    expect(trigger).toHaveTextContent("Codex");
    expect(marks(trigger)).toEqual(["openai-blossom"]);
  });

  test("a filter option can carry a mark that is not part of its name", async () => {
    render(
      <FilterPill
        label="By"
        options={[
          {
            value: "u-cc",
            label: "Claude Code",
            icon: <span data-agent-mark="claude-spark" />,
          },
        ]}
        value={[]}
        onChange={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: "By" }));
    const option = screen.getByRole("option", { name: "Claude Code" });
    expect(marks(option)).toEqual(["claude-spark"]);
  });
});
