// frontend/src/components/agents/AgentMcpControls.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ApiError } from "@/lib/api/errors";
import { AgentMcpButton, AgentMcpStatusBadge } from "./AgentMcpControls";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentMcpStatus: vi.fn(),
  useAgentMcpInstall: vi.fn(),
}));
const { useAgentMcpStatus, useAgentMcpInstall } = await import("@/lib/hooks/useAgents");
const statusMock = vi.mocked(useAgentMcpStatus);
const installMock = vi.mocked(useAgentMcpInstall);

function stub(installed: boolean, mutate = vi.fn(), error: unknown = null) {
  statusMock.mockReturnValue({
    data: { installed, command: installed ? "/opt/coffer-mcp-shim" : null },
    isPending: false,
  } as unknown as ReturnType<typeof useAgentMcpStatus>);
  installMock.mockReturnValue({
    mutate,
    isPending: false,
    error,
  } as unknown as ReturnType<typeof useAgentMcpInstall>);
  return mutate;
}

afterEach(() => vi.clearAllMocks());

describe("AgentMcpButton", () => {
  test("not installed → Install button triggers install", () => {
    const mutate = stub(false);
    render(<AgentMcpButton name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /install coffer mcp/i }));
    expect(mutate).toHaveBeenCalledWith(true);
  });

  test("installed → Uninstall button triggers uninstall", () => {
    const mutate = stub(true);
    render(<AgentMcpButton name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /uninstall/i }));
    expect(mutate).toHaveBeenCalledWith(false);
  });

  test("surfaces a mutation error inline instead of looking like a no-op", () => {
    stub(false, vi.fn(), new ApiError("SHIM_NOT_FOUND", "raw server message"));
    render(<AgentMcpButton name="cur" />);
    expect(screen.getByText(/coffer-mcp-shim/i)).toBeInTheDocument();
  });
});

describe("AgentMcpStatusBadge", () => {
  test("reflects installed / not-installed", () => {
    stub(true);
    const { rerender } = render(<AgentMcpStatusBadge name="cur" />);
    expect(screen.getByText(/^installed$/i)).toBeInTheDocument();
    stub(false);
    rerender(<AgentMcpStatusBadge name="cur" />);
    expect(screen.getByText(/not installed/i)).toBeInTheDocument();
  });
});
