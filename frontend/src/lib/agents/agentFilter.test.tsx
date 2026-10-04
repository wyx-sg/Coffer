// src/lib/agents/agentFilter.test.tsx — `?agent=<uid>` on the Skills and MCP servers pages: the filter and the Reach select that writes it.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import "@/i18n";
import { AgentReachFilter } from "@/components/reach/AgentReachFilter";
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
      <AgentReachFilter filter={filter} />
    </>
  );
}

describe("useAgentFilter", () => {
  test("no ?agent= means no filter, and Reach reads All", () => {
    render(
      <MemoryRouter initialEntries={["/skills"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("matches")).toHaveTextContent("undefined/undefined/undefined");
    expect(screen.getByRole("combobox", { name: "Reach" })).toHaveTextContent("All");
  });

  acceptance("agent-registry", "the global lists narrow to one agent", async () => {
    render(
      <MemoryRouter initialEntries={["/skills?agent=u-cc&x=1"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("matches")).toHaveTextContent("true/false/true");
    const reach = screen.getByRole("combobox", { name: "Reach" });
    expect(reach).toHaveTextContent("Claude Code");
    // Radix Select opens from the keyboard in jsdom (no PointerEvent).
    fireEvent.keyDown(reach, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "All" }));
    await waitFor(() => expect(screen.getByTestId("search")).toHaveTextContent("?x=1"));
    expect(screen.getByTestId("matches")).toHaveTextContent("undefined/undefined/undefined");
  });
});
