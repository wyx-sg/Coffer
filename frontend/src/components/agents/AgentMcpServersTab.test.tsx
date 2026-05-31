// frontend/src/components/agents/AgentMcpServersTab.test.tsx
//
// The MCP-servers tab shows a "Managed by Coffer" section listing the enabled
// mcp_server resources Coffer exposes to this agent, as a READ-ONLY table (no
// per-server toggle — that's Coffer-global; per-agent control is a planned
// Layer-2 feature). When Coffer's MCP isn't installed, a prerequisite note
// replaces the list.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AgentMcpServersTab } from "./AgentMcpServersTab";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentMcpStatus: vi.fn(),
}));
vi.mock("@/lib/hooks/useResources", () => ({
  useResources: vi.fn(() => ({
    data: [
      {
        ref: { kind: "mcp_server", name: "fs" },
        kind: "mcp_server",
        name: "fs",
        description: null,
        config: {},
        enabled: true,
        created_at: "",
        updated_at: "",
      },
    ],
    isPending: false,
    error: null,
  })),
}));

const { useAgentMcpStatus } = await import("@/lib/hooks/useAgents");
const statusMock = vi.mocked(useAgentMcpStatus);

function stubInstalled(installed: boolean) {
  statusMock.mockReturnValue({
    data: { installed, command: installed ? "/opt/coffer-mcp-shim" : null },
    isPending: false,
  } as unknown as ReturnType<typeof useAgentMcpStatus>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentMcpServersTab", () => {
  test("installed → lists the exposed MCP server read-only (no toggle)", () => {
    stubInstalled(true);
    render(
      <MemoryRouter>
        <AgentMcpServersTab agentName="cc" />
      </MemoryRouter>,
    );
    expect(screen.getByText("fs")).toBeInTheDocument();
    // Read-only: no per-server enable/disable toggle on the agent page.
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  test("not installed → shows the prerequisite note instead of the list", () => {
    stubInstalled(false);
    render(
      <MemoryRouter>
        <AgentMcpServersTab agentName="cc" />
      </MemoryRouter>,
    );
    expect(screen.getByText(/coffer mcp isn't installed on this agent/i)).toBeInTheDocument();
    expect(screen.queryByText("fs")).not.toBeInTheDocument();
  });
});
