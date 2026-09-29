// frontend/src/components/agents/AgentConnectionControls.test.tsx
// Connecting is one click; disconnecting asks first (it cuts the agent off from
// the gateway); a partial connection reads "Needs repair" and offers Connect,
// which puts the missing parts back. Failures toast from the hook (covered in
// useAgents.test), so nothing renders inline here.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ToastProvider } from "@/components/ui/toast";
import type { CofferConnection } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";
import { AgentConnectionBadge, AgentConnectionButton } from "./AgentConnectionControls";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentConnection: vi.fn(),
  useAgentConnect: vi.fn(),
}));
const { useAgentConnection, useAgentConnect } = await import("@/lib/hooks/useAgents");
const statusMock = vi.mocked(useAgentConnection);
const connectMock = vi.mocked(useAgentConnect);

const CONNECTED: CofferConnection = {
  state: "connected",
  parts: [
    { key: "mcp", installed: true, detail: "/opt/coffer-mcp-shim" },
    { key: "memory_hook", installed: true, detail: ": coffer-memory; coffer memory context" },
  ],
};
const PARTIAL: CofferConnection = {
  state: "partial",
  parts: [
    { key: "mcp", installed: true, detail: "/opt/coffer-mcp-shim" },
    { key: "memory_hook", installed: false, detail: null },
  ],
};
const DISCONNECTED: CofferConnection = {
  state: "disconnected",
  parts: [
    { key: "mcp", installed: false, detail: null },
    { key: "memory_hook", installed: false, detail: null },
  ],
};

function stub(data: CofferConnection | undefined, mutate = vi.fn(), isPending = false) {
  statusMock.mockReturnValue({ data, isPending } as unknown as ReturnType<
    typeof useAgentConnection
  >);
  connectMock.mockReturnValue({
    mutate,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useAgentConnect>);
  return mutate;
}

function renderButton() {
  return render(
    <ToastProvider>
      <AgentConnectionButton uid="u-cur" />
    </ToastProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentConnectionButton", () => {
  acceptance("agent-registry", "the header offers the action the state calls for", () => {
    stub(DISCONNECTED);
    const { unmount } = renderButton();
    expect(screen.getByRole("button", { name: /^connect to coffer$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /disconnect/i })).toBeNull();
    expect(screen.queryByText(/needs repair/i)).toBeNull();
    unmount();

    stub(CONNECTED);
    const connected = renderButton();
    expect(screen.getByRole("button", { name: /disconnect from coffer/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^connect to coffer$/i })).toBeNull();
    connected.unmount();

    stub(PARTIAL);
    renderButton();
    expect(screen.getByText(/needs repair/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^connect to coffer$/i })).toBeInTheDocument();
  });

  test("connecting is one click and toasts on success", () => {
    const mutate = vi.fn((_connect: boolean, opts?: { onSuccess?: () => void }) =>
      opts?.onSuccess?.(),
    );
    stub(DISCONNECTED, mutate);
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: /^connect to coffer$/i }));
    expect(mutate).toHaveBeenCalledWith(true, expect.anything());
    expect(screen.getByRole("status")).toHaveTextContent(/connected to coffer/i);
  });

  test("a partial connection's Connect re-applies the connection", () => {
    const mutate = stub(PARTIAL);
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: /^connect to coffer$/i }));
    expect(mutate).toHaveBeenCalledWith(true, expect.anything());
  });

  test("disconnecting asks for confirmation first", () => {
    const mutate = stub(CONNECTED);
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: /disconnect from coffer/i }));
    expect(mutate).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/disconnect from coffer\?/i);
    fireEvent.click(within(dialog).getByRole("button", { name: /disconnect from coffer/i }));
    expect(mutate).toHaveBeenCalledWith(false, expect.anything());
  });

  test("cancelling the disconnect dialog is a no-op", () => {
    const mutate = stub(CONNECTED);
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: /disconnect from coffer/i }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
  });

  test("the parts live behind the help button, not inline", async () => {
    stub(PARTIAL);
    renderButton();
    expect(screen.queryByText(/gateway mcp entry/i)).toBeNull();
    const help = screen.getByRole("button", { name: /what connecting installs/i });
    fireEvent.focus(help);
    expect((await screen.findAllByText(/gateway mcp entry/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/memory delivery hook/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/connect again to put them back/i).length).toBeGreaterThan(0);
  });

  test("with memory off the help says the hook comes with Memory", async () => {
    stub({ state: "connected", parts: [CONNECTED.parts[0]] });
    renderButton();
    fireEvent.focus(screen.getByRole("button", { name: /what connecting installs/i }));
    expect(
      (await screen.findAllByText(/added while memory is switched on/i)).length,
    ).toBeGreaterThan(0);
  });
});

describe("AgentConnectionBadge", () => {
  test("reads Connected / Not connected / Needs repair", () => {
    stub(CONNECTED);
    const { rerender } = render(<AgentConnectionBadge uid="u-cur" />);
    expect(screen.getByText(/^connected$/i)).toBeInTheDocument();
    stub(DISCONNECTED);
    rerender(<AgentConnectionBadge uid="u-cur" />);
    expect(screen.getByText(/^not connected$/i)).toBeInTheDocument();
    stub(PARTIAL);
    rerender(<AgentConnectionBadge uid="u-cur" />);
    expect(screen.getByText(/^needs repair$/i)).toBeInTheDocument();
  });

  test("shows a labelled placeholder while the status loads", () => {
    stub(undefined, vi.fn(), true);
    render(<AgentConnectionBadge uid="u-cur" />);
    expect(document.querySelector("[aria-label='Checking…']")).not.toBeNull();
  });
});
