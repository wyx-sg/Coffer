// frontend/src/components/agents/AgentHookControls.test.tsx — slice 6.
// The session-start hook control mirrors the Coffer-MCP control: Install (POST)
// / Uninstall (DELETE) with pending + inline error, plus the 422
// HOOK_INSTALL_UNSUPPORTED state where the agent type has no hook support.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ApiError } from "@/lib/api/errors";
import { AgentHookButton } from "./AgentHookControls";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentHookStatus: vi.fn(),
  useAgentHookInstall: vi.fn(),
}));
const { useAgentHookStatus, useAgentHookInstall } = await import("@/lib/hooks/useAgents");
const statusMock = vi.mocked(useAgentHookStatus);
const installMock = vi.mocked(useAgentHookInstall);

function stub(
  installed: boolean,
  mutate = vi.fn(),
  opts: { mutateError?: unknown; statusError?: unknown } = {},
) {
  statusMock.mockReturnValue({
    data: opts.statusError
      ? undefined
      : { installed, command: installed ? "/opt/coffer-hook-shim" : null },
    isPending: false,
    error: opts.statusError ?? null,
  } as unknown as ReturnType<typeof useAgentHookStatus>);
  installMock.mockReturnValue({
    mutate,
    isPending: false,
    error: opts.mutateError ?? null,
  } as unknown as ReturnType<typeof useAgentHookInstall>);
  return mutate;
}

afterEach(() => vi.clearAllMocks());

describe("AgentHookButton", () => {
  test("not installed → Install button triggers install (POST)", () => {
    const mutate = stub(false);
    render(<AgentHookButton name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /inject rules at session start/i }));
    expect(mutate).toHaveBeenCalledWith(true);
  });

  test("installed → Uninstall button triggers uninstall (DELETE)", () => {
    const mutate = stub(true);
    render(<AgentHookButton name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /stop injecting rules/i }));
    expect(mutate).toHaveBeenCalledWith(false);
  });

  test("surfaces a mutation error inline instead of looking like a no-op", () => {
    stub(false, vi.fn(), { mutateError: new ApiError("SHIM_NOT_FOUND", "shim binary missing") });
    render(<AgentHookButton name="cur" />);
    // SHIM_NOT_FOUND has an i18n entry, so the inline error shows the translated
    // shim message rather than the raw envelope text.
    expect(screen.getByText(/coffer-mcp-shim/i)).toBeInTheDocument();
  });

  test("422 HOOK_INSTALL_UNSUPPORTED → disabled control + explanatory text, no action", () => {
    const mutate = stub(false, vi.fn(), {
      statusError: new ApiError("HOOK_INSTALL_UNSUPPORTED", "no hook support"),
    });
    render(<AgentHookButton name="cur" />);
    const btn = screen.getByRole("button", { name: /inject rules at session start/i });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/doesn't support a session-start hook/i)).toBeInTheDocument();
    fireEvent.click(btn);
    expect(mutate).not.toHaveBeenCalled();
  });
});
