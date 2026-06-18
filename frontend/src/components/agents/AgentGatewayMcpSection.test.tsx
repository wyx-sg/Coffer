// frontend/src/components/agents/AgentGatewayMcpSection.test.tsx
//
// Tests for the per-agent MCP-scope editor (Section A of the agent MCP tab):
//   - not-installed / empty states still render their notes
//   - auto mode shows the explanation and NO per-server checkboxes
//   - selected mode renders a checkbox per enabled server with the
//     allowlisted ones checked
//   - Save calls putAgentMcpScope with the chosen mode + checked servers
//   - a 422 (unknown server) surfaces the friendly unknown-server message
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentGatewayMcpSection } from "./AgentGatewayMcpSection";
import { ApiError } from "@/lib/api/errors";
import type { AgentMcpScope } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/components/kindRegistry";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: { mcpStatus: vi.fn() },
  getAgentMcpScope: vi.fn(),
  putAgentMcpScope: vi.fn(),
}));

const resourcesState: {
  data: ResourceOut[];
  isPending: boolean;
  error: unknown;
} = { data: [], isPending: false, error: null };
vi.mock("@/lib/hooks/useResources", () => ({
  useResources: vi.fn(() => resourcesState),
}));

const mcpStatusState: { data: { installed: boolean }; isPending: boolean } = {
  data: { installed: true },
  isPending: false,
};
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentMcpStatus: vi.fn(() => mcpStatusState),
}));

const { getAgentMcpScope, putAgentMcpScope } = await import("@/lib/api/agents");
const getScope = vi.mocked(getAgentMcpScope);
const putScope = vi.mocked(putAgentMcpScope);

function mkServer(name: string, enabled = true): ResourceOut {
  return {
    ref: `mcp_server/${name}`,
    kind: "mcp_server",
    name,
    description: null,
    config: {},
    enabled,
    created_at: "",
    updated_at: "",
  } as ResourceOut;
}

const SERVERS = [mkServer("fs"), mkServer("github"), mkServer("disabled", false)];

function render_(agentName = "cc") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(<AgentGatewayMcpSection agentName={agentName} />, { wrapper: Wrapper });
}

beforeEach(() => {
  resourcesState.data = SERVERS;
  resourcesState.isPending = false;
  resourcesState.error = null;
  mcpStatusState.data = { installed: true };
  mcpStatusState.isPending = false;
  getScope.mockResolvedValue({ mode: "auto", servers: [] });
  putScope.mockImplementation(async (_name, scope: AgentMcpScope) => scope);
});

afterEach(() => vi.clearAllMocks());

describe("AgentGatewayMcpSection", () => {
  test("not-installed state shows the install note and no scope controls", async () => {
    mcpStatusState.data = { installed: false };
    render_();
    expect(
      await screen.findByText(/coffer mcp isn't installed on this agent/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("auto mode renders the explanation and no per-server checkboxes", async () => {
    getScope.mockResolvedValue({ mode: "auto", servers: [] });
    render_();

    // Auto explanation copy is shown.
    expect(
      await screen.findByText(/every enabled mcp server is exposed to this agent/i),
    ).toBeInTheDocument();
    // Enabled servers still listed, but no per-server checkbox column.
    expect(screen.getByText("fs")).toBeInTheDocument();
    expect(screen.getByText("github")).toBeInTheDocument();
    // The disabled resource is filtered out.
    expect(screen.queryByText("disabled")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("selected mode renders a checkbox per enabled server with allowlisted ones checked", async () => {
    getScope.mockResolvedValue({ mode: "selected", servers: ["fs"] });
    render_();

    // One checkbox per ENABLED server (2), not the disabled one.
    const boxes = await screen.findAllByRole("checkbox");
    expect(boxes).toHaveLength(2);

    const fsBox = screen.getByRole("checkbox", { name: /selected servers: fs/i });
    const ghBox = screen.getByRole("checkbox", { name: /selected servers: github/i });
    expect(fsBox).toBeChecked();
    expect(ghBox).not.toBeChecked();
  });

  test("empty enabled-servers list still shows the empty note", async () => {
    resourcesState.data = [mkServer("only-disabled", false)];
    getScope.mockResolvedValue({ mode: "auto", servers: [] });
    render_();
    expect(
      await screen.findByText(/no enabled mcp servers in coffer to expose/i),
    ).toBeInTheDocument();
  });

  test("Save calls putAgentMcpScope with the chosen mode + checked servers", async () => {
    getScope.mockResolvedValue({ mode: "selected", servers: ["fs"] });
    render_("my-agent");

    const ghBox = await screen.findByRole("checkbox", { name: /selected servers: github/i });
    // Add github to the allowlist.
    fireEvent.click(ghBox);

    fireEvent.click(screen.getByRole("button", { name: /save scope/i }));
    await waitFor(() => expect(putScope).toHaveBeenCalledTimes(1));
    const [name, scope] = putScope.mock.calls[0];
    expect(name).toBe("my-agent");
    expect(scope.mode).toBe("selected");
    expect([...scope.servers].sort()).toEqual(["fs", "github"]);

    // Success copy appears once the save settles.
    expect(await screen.findByText(/scope saved/i)).toBeInTheDocument();
  });

  test("switching to auto saves an empty allowlist", async () => {
    getScope.mockResolvedValue({ mode: "selected", servers: ["fs"] });
    render_();

    fireEvent.click(await screen.findByRole("radio", { name: /all servers/i }));
    fireEvent.click(screen.getByRole("button", { name: /save scope/i }));

    await waitFor(() => expect(putScope).toHaveBeenCalledTimes(1));
    expect(putScope.mock.calls[0][1]).toEqual({ mode: "auto", servers: [] });
  });

  test("a 422 unknown-server error surfaces the friendly message", async () => {
    getScope.mockResolvedValue({ mode: "selected", servers: ["fs"] });
    putScope.mockRejectedValue(
      new ApiError("MCP_SCOPE_SERVER_UNKNOWN", "server 'gone' does not exist"),
    );
    render_();

    // Make the form dirty so Save is enabled.
    fireEvent.click(await screen.findByRole("checkbox", { name: /selected servers: github/i }));
    fireEvent.click(screen.getByRole("button", { name: /save scope/i }));

    expect(
      await screen.findByText(/one of the selected servers no longer exists/i),
    ).toBeInTheDocument();
  });
});
