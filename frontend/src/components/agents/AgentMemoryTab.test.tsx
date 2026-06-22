// frontend/src/components/agents/AgentMemoryTab.test.tsx
//
// The "Memory" tab on the agent detail page has two sections: (A) a "Managed by
// Coffer" card reached via the Coffer MCP gateway — it links to the standalone
// Memory page when Coffer MCP is installed, or shows the not-installed note
// otherwise; and (B) a table of the agent's OWN native per-project memory stores
// (project / path / item count), read-only with open / reveal actions — independent
// of the gateway. We mock useAgentNativeMemory + useAgentMcpStatus + useNavigate.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentMemoryTab } from "./AgentMemoryTab";
import type { AgentOut, NativeMemoryStore } from "@/lib/api/agents";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

const importMutate = vi.fn();
const patchMutate = vi.fn();

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentNativeMemory: vi.fn(),
  useAgentMcpStatus: vi.fn(),
  useImportNativeMemory: vi.fn(() => ({ mutate: importMutate, isPending: false })),
  usePatchAgent: vi.fn(() => ({ mutate: patchMutate, isPending: false })),
  // The session-start rules-injection card now lives in this tab; stub its
  // status/install hooks so the card renders (not-installed, idle) without error.
  useAgentHookStatus: vi.fn(() => ({ data: { installed: false }, isPending: false, error: null })),
  useAgentHookInstall: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
}));
const hooks = await import("@/lib/hooks/useAgents");

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
  vi.mocked(hooks.useAgentNativeMemory).mockReturnValue({
    data: { items },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useAgentNativeMemory>);
}

function stubMcp(installed: boolean) {
  vi.mocked(hooks.useAgentMcpStatus).mockReturnValue({
    data: { installed, command: installed ? "/shim" : null },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useAgentMcpStatus>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentMemoryTab", () => {
  test("with Coffer MCP installed, shows the access-via-gateway note", () => {
    stubMcp(true);
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/accesses coffer memory via the mcp gateway/i)).toBeInTheDocument();
  });

  test("the Coffer-managed card links to the standalone Memory page", () => {
    stubMcp(true);
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /open the memory page/i }));
    expect(navigateMock).toHaveBeenCalledWith("/memory");
  });

  test("without Coffer MCP installed, shows the not-installed note and no link", () => {
    stubMcp(false);
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/coffer mcp isn't installed on this agent/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open the memory page/i })).not.toBeInTheDocument();
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
    expect(
      screen.getByText("/Users/xing/.claude/projects/-Users-xing-Coffer/memory"),
    ).toBeInTheDocument();
    expect(screen.getByText("49")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  test("shows the empty message when the agent has no native memory stores", () => {
    stubMcp(true);
    stubNative([]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/no native memory stores/i)).toBeInTheDocument();
  });

  test("clicking Import to Coffer imports the store's memory dir", () => {
    stubMcp(true);
    stubNative([COFFER_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /import to coffer/i }));
    expect(importMutate).toHaveBeenCalledWith(COFFER_STORE.memory_dir, expect.anything());
  });

  test("disable-native-memory toggle reflects the agent flag and PATCHes on flip", () => {
    stubMcp(true);
    stubNative([COFFER_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    const toggle = screen.getByRole("switch", { name: /disable this agent's native memory/i });
    // Reads agent.disable_native_memory (undefined → off).
    expect(toggle).toHaveAttribute("aria-checked", "false");
    fireEvent.click(toggle);
    expect(patchMutate).toHaveBeenCalledWith(
      { name: AGENT.name, body: { disable_native_memory: true } },
      expect.anything(),
    );
  });

  test("disable-native-memory toggle shows as on when the agent has it disabled", () => {
    stubMcp(true);
    stubNative([COFFER_STORE]);
    render(<AgentMemoryTab agent={{ ...AGENT, disable_native_memory: true }} />, { wrapper: wrap });
    const toggle = screen.getByRole("switch", { name: /disable this agent's native memory/i });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    fireEvent.click(toggle);
    expect(patchMutate).toHaveBeenCalledWith(
      { name: AGENT.name, body: { disable_native_memory: false } },
      expect.anything(),
    );
  });
});
