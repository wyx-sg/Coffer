// src/lib/agents/agentFilter.test.tsx — `?agent=<uid>` on the Skills and MCP servers pages: a filter plus a removable pill.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import "@/i18n";
import { AgentFilterPill } from "@/components/agents/tabs/AgentFilterPill";
import { acceptance } from "@/test/acceptance";
import { useAgentFilter } from "./agentFilter";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({ data: [{ uid: "u-cc", type: "claude_code", name: "claude_code" }] }),
}));

function Probe() {
  const filter = useAgentFilter();
  const { search } = useLocation();
  return (
    <>
      <p data-testid="matches">
        {String(filter?.matches({ enabled: true, scope: { agents: ["u-cc"] } }))}/
        {String(filter?.matches({ enabled: true, scope: { agents: ["u-cx"] } }))}/
        {String(filter?.matches({ enabled: true, scope: null }))}
      </p>
      <p data-testid="search">{search}</p>
      <AgentFilterPill filter={filter} />
    </>
  );
}

describe("useAgentFilter", () => {
  test("no ?agent= means no filter and no pill", () => {
    render(
      <MemoryRouter initialEntries={["/skills"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("matches")).toHaveTextContent("undefined/undefined/undefined");
    expect(screen.queryByText(/Agent:/)).toBeNull();
  });

  acceptance("agent-registry", "the global lists narrow to one agent", () => {
    render(
      <MemoryRouter initialEntries={["/skills?agent=u-cc&x=1"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("matches")).toHaveTextContent("true/false/true");
    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove the Claude Code filter" }));
    expect(screen.getByTestId("search")).toHaveTextContent("?x=1");
    expect(screen.queryByText(/Agent:/)).toBeNull();
  });
});
