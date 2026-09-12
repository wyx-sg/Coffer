// frontend/src/components/agents/AgentMemoryTab.test.tsx
//
// The "Memory" tab on the agent detail page has two read-only sections: (A) a
// "Managed by Coffer" card reached via the Coffer MCP gateway — it links to the
// standalone Knowledge page when Coffer MCP is installed, or shows the
// not-installed note otherwise; and (B) a table of the agent's OWN native
// per-project memory stores (project / path / item count) with open / reveal
// row actions — independent of the gateway. We mock the two hooks at the network
// boundary (useAgentNativeMemory + useAgentMcpStatus) and useNavigate.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentMemoryTab } from "./AgentMemoryTab";
import type { AgentOut } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

vi.mock("@/lib/hooks/useAgentNativeMemory", () => ({
  useAgentNativeMemory: vi.fn(),
  agentNativeMemoryKey: (name: string) => ["agents", name, "native-memory"],
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgentMcpStatus: vi.fn() }));

const nativeHooks = await import("@/lib/hooks/useAgentNativeMemory");
const agentHooks = await import("@/lib/hooks/useAgents");

// The row actions call the daemon through useFsActions; stub that boundary so a
// click asserts the request we make, not the transport.
const openMock = vi.fn(() => Promise.resolve());
const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: revealMock }),
}));

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const AGENT: AgentOut = {
  name: "claude",
  type: "claude_code",
  config_dir: "/home/u/.claude",
  description: null,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

const COFFER_STORE: NativeMemoryStore = {
  project: "Coffer",
  path: "/Users/xing/Coffer",
  memory_dir: "/Users/xing/.claude/projects/-Users-xing-Coffer/memory",
  item_count: 49,
};

const DEVPILOT_STORE: NativeMemoryStore = {
  project: "DevPilot",
  path: "/Users/xing/DevPilot",
  memory_dir: "/Users/xing/.claude/projects/-Users-xing-DevPilot/memory",
  item_count: 8,
};

function stubNative(items: NativeMemoryStore[] = [COFFER_STORE]) {
  vi.mocked(nativeHooks.useAgentNativeMemory).mockReturnValue({
    data: { items },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof nativeHooks.useAgentNativeMemory>);
}

function stubMcp(installed: boolean) {
  vi.mocked(agentHooks.useAgentMcpStatus).mockReturnValue({
    data: { installed, command: installed ? "/shim" : null },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof agentHooks.useAgentMcpStatus>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentMemoryTab", () => {
  test("with Coffer MCP installed, shows the access-via-gateway note", () => {
    stubMcp(true);
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(
      screen.getByText(/reaches coffer's knowledge through the mcp gateway/i),
    ).toBeInTheDocument();
  });

  test("the Coffer-managed card links to the standalone Knowledge page", () => {
    stubMcp(true);
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /open the knowledge page/i }));
    expect(navigateMock).toHaveBeenCalledWith("/knowledge");
  });

  test("without Coffer MCP installed, shows the not-installed note and no link", () => {
    stubMcp(false);
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/coffer mcp isn't installed on this agent/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /open the knowledge page/i }),
    ).not.toBeInTheDocument();
    // Section B (the agent's own native memory) is independent of the gateway —
    // it still renders when Coffer MCP is not installed.
    expect(screen.getByText("Coffer")).toBeInTheDocument();
  });

  test("renders the agent's native per-project memory stores as a table", () => {
    stubMcp(true);
    stubNative([COFFER_STORE, DEVPILOT_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });

    expect(screen.getByText("Coffer")).toBeInTheDocument();
    expect(screen.getByText("DevPilot")).toBeInTheDocument();
    // The path column shows the real project path (s.path), not the internal
    // memory_dir — so Codex rows sharing one memory_dir stay distinguishable.
    expect(screen.getByText("/Users/xing/Coffer")).toBeInTheDocument();
    expect(screen.getByText("49")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  test("falls back to the memory dir when the project path could not be resolved", () => {
    stubMcp(true);
    stubNative([{ ...COFFER_STORE, path: null }]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(COFFER_STORE.memory_dir)).toBeInTheDocument();
  });

  test("the tab is read-only — no import or bulk-selection affordances", () => {
    stubMcp(true);
    stubNative([COFFER_STORE, DEVPILOT_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.queryByRole("button", { name: /import/i })).not.toBeInTheDocument();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  test("the row menu opens the store's directory in the editor", () => {
    stubMcp(true);
    stubNative([COFFER_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /more actions/i }));
    fireEvent.click(screen.getByText(/open in editor/i));
    expect(openMock).toHaveBeenCalledWith(COFFER_STORE.memory_dir, expect.anything());
  });

  test("the row menu reveals the store's directory in the file manager", () => {
    stubMcp(true);
    stubNative([COFFER_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /more actions/i }));
    fireEvent.click(screen.getByText(/reveal in finder/i));
    expect(revealMock).toHaveBeenCalledWith(COFFER_STORE.memory_dir);
  });

  test("shows the empty message when the agent has no native memory stores", () => {
    stubMcp(true);
    stubNative([]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/no native memory stores/i)).toBeInTheDocument();
  });
});
