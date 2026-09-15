// frontend/src/components/agents/AgentMcpControls.test.tsx
// Install is one click; uninstall asks first (it cuts the agent off from the
// gateway); either success is confirmed with a toast. Failures toast from the
// hook (covered in useAgents.test), so nothing renders inline here.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { ToastProvider } from "@/components/ui/toast";
import { AgentMcpButton, AgentMcpStatusBadge } from "./AgentMcpControls";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentMcpStatus: vi.fn(),
  useAgentMcpInstall: vi.fn(),
}));
const { useAgentMcpStatus, useAgentMcpInstall } = await import("@/lib/hooks/useAgents");
const statusMock = vi.mocked(useAgentMcpStatus);
const installMock = vi.mocked(useAgentMcpInstall);

function stub(installed: boolean, mutate = vi.fn(), isPending = false) {
  statusMock.mockReturnValue({
    data: { installed, command: installed ? "/opt/coffer-mcp-shim" : null },
    isPending,
  } as unknown as ReturnType<typeof useAgentMcpStatus>);
  installMock.mockReturnValue({
    mutate,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useAgentMcpInstall>);
  return mutate;
}

function renderWithToasts(ui: React.ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentMcpButton", () => {
  test("not installed → Install button installs at once and toasts on success", () => {
    const mutate = vi.fn((_install: boolean, opts?: { onSuccess?: () => void }) =>
      opts?.onSuccess?.(),
    );
    stub(false, mutate);
    renderWithToasts(<AgentMcpButton name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /install coffer mcp/i }));
    expect(mutate).toHaveBeenCalledWith(true, expect.anything());
    expect(screen.getByRole("status")).toHaveTextContent(/coffer mcp installed/i);
  });

  test("installed → Uninstall asks for confirmation before uninstalling", () => {
    const mutate = stub(true);
    renderWithToasts(<AgentMcpButton name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /uninstall coffer mcp/i }));
    // Nothing happens until the dialog is confirmed.
    expect(mutate).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/uninstall coffer mcp\?/i);
    fireEvent.click(within(dialog).getByRole("button", { name: /uninstall coffer mcp/i }));
    expect(mutate).toHaveBeenCalledWith(false, expect.anything());
  });

  test("cancelling the uninstall dialog is a no-op", () => {
    const mutate = stub(true);
    renderWithToasts(<AgentMcpButton name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /uninstall coffer mcp/i }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
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

  test("shows a labelled placeholder while the status loads, not an ellipsis", () => {
    stub(false, vi.fn(), true);
    render(<AgentMcpStatusBadge name="cur" />);
    expect(screen.queryByText("…")).not.toBeInTheDocument();
    expect(document.querySelector("[aria-label='Checking…']")).not.toBeNull();
  });
});
