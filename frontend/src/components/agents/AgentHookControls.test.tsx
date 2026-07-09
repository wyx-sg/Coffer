// frontend/src/components/agents/AgentHookControls.test.tsx — slice 6.
// The session-start hook toggle: switching on installs (POST) / off uninstalls
// (DELETE) with pending + inline error, plus the unsupported state where the
// agent type has no hook support (disabled switch + note). Unsupported is
// signalled by `status.supported === false` — status succeeds, it does not 422;
// the legacy 422 path is kept as a fallback for an older daemon.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ApiError } from "@/lib/api/errors";
import { AgentHookToggle } from "./AgentHookControls";

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
  opts: { mutateError?: unknown; statusError?: unknown; supported?: boolean } = {},
) {
  statusMock.mockReturnValue({
    data: opts.statusError
      ? undefined
      : {
          installed,
          command: installed ? "/opt/coffer-hook-shim" : null,
          supported: opts.supported ?? true,
        },
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

describe("AgentHookToggle", () => {
  test("not installed → switching on installs (POST)", () => {
    const mutate = stub(false);
    render(<AgentHookToggle name="cur" />);
    const sw = screen.getByRole("switch", { name: /session-start rules/i });
    expect(sw).toHaveAttribute("aria-checked", "false");
    fireEvent.click(sw);
    expect(mutate).toHaveBeenCalledWith(true);
  });

  test("installed → switching off uninstalls (DELETE)", () => {
    const mutate = stub(true);
    render(<AgentHookToggle name="cur" />);
    const sw = screen.getByRole("switch", { name: /session-start rules/i });
    expect(sw).toHaveAttribute("aria-checked", "true");
    fireEvent.click(sw);
    expect(mutate).toHaveBeenCalledWith(false);
  });

  test("surfaces a mutation error inline instead of looking like a no-op", () => {
    stub(false, vi.fn(), { mutateError: new ApiError("SHIM_NOT_FOUND", "shim binary missing") });
    render(<AgentHookToggle name="cur" />);
    // SHIM_NOT_FOUND has an i18n entry, so the inline error shows the translated
    // shim message rather than the raw envelope text.
    expect(screen.getByText(/coffer-mcp-shim/i)).toBeInTheDocument();
  });

  test("422 HOOK_INSTALL_UNSUPPORTED → disabled switch + explanatory text, no action", () => {
    const mutate = stub(false, vi.fn(), {
      statusError: new ApiError("HOOK_INSTALL_UNSUPPORTED", "no hook support"),
    });
    render(<AgentHookToggle name="cur" />);
    const sw = screen.getByRole("switch", { name: /session-start rules/i });
    expect(sw).toBeDisabled();
    expect(screen.getByText(/doesn't support a session-start hook/i)).toBeInTheDocument();
    fireEvent.click(sw);
    expect(mutate).not.toHaveBeenCalled();
  });
});

describe("unsupported agent types", () => {
  test("a successful status with supported:false disables the switch", () => {
    const mutate = vi.fn();
    stub(false, mutate, { supported: false });
    render(<AgentHookToggle name="oc" />);
    const sw = screen.getByRole("switch");
    expect(sw).toBeDisabled();
    // The control must never fire a mutation that would 422.
    fireEvent.click(sw);
    expect(mutate).not.toHaveBeenCalled();
  });

  test("supported:true renders an enabled switch", () => {
    stub(false, vi.fn(), { supported: true });
    render(<AgentHookToggle name="cur" />);
    expect(screen.getByRole("switch")).toBeEnabled();
  });

  test("legacy 422 status error still disables the switch", () => {
    stub(false, vi.fn(), {
      statusError: new ApiError("HOOK_INSTALL_UNSUPPORTED", "not supported"),
    });
    render(<AgentHookToggle name="oc" />);
    expect(screen.getByRole("switch")).toBeDisabled();
  });
});
