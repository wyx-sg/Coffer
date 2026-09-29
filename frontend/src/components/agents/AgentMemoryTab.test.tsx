// frontend/src/components/agents/AgentMemoryTab.test.tsx
//
// The Memory tab lists only the agent's own native memory stores, read-only:
// a heading with the count, a line saying Coffer only reads them, and a table
// of project, path and item count whose row opens the store's page (addressed
// by the agent's type and the store's directory). There is no Coffer-memory
// pointer, no delivery-hook action and no per-row action. The hook is mocked
// at the network boundary.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentMemoryTab } from "./AgentMemoryTab";
import type { AgentOut } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));
vi.mock("@/lib/hooks/useAgentNativeMemory", () => ({ useAgentNativeMemory: vi.fn() }));
const nativeHooks = await import("@/lib/hooks/useAgentNativeMemory");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const AGENT = {
  uid: "agt_01cc",
  name: "claude_code",
  type: "claude_code",
  config_dir: "/Users/xing/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  wire_api: null,
  version: null,
  state: "installed_active",
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
} as AgentOut;

const CODEX = {
  ...AGENT,
  uid: "agt_01cx",
  type: "codex",
  config_dir: "/Users/xing/.codex",
} as AgentOut;

const COFFER_STORE: NativeMemoryStore = {
  project: "Coffer",
  path: "/Users/xing/Coffer",
  memory_dir: "/Users/xing/.claude/projects/-Users-xing-Coffer/memory",
  item_count: 49,
};

function stubNative(items: NativeMemoryStore[] = [COFFER_STORE], extra: object = {}) {
  vi.mocked(nativeHooks.useAgentNativeMemory).mockReturnValue({
    data: { items },
    isPending: false,
    error: null,
    refetch: vi.fn(),
    ...extra,
  } as unknown as ReturnType<typeof nativeHooks.useAgentNativeMemory>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentMemoryTab", () => {
  test("lists the native stores with project, path and item count", () => {
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(vi.mocked(nativeHooks.useAgentNativeMemory)).toHaveBeenCalledWith("agt_01cc");
    expect(screen.getByRole("heading", { name: "Native memory stores · 1" })).toBeInTheDocument();
    expect(screen.getByText(/coffer reads them to build shared memory/i)).toBeInTheDocument();
    expect(screen.getByText("~/Coffer")).toBeInTheDocument();
    expect(screen.getByText("~/.claude/projects/-Users-xing-Coffer/memory")).toBeInTheDocument();
    expect(screen.getByText("49")).toBeInTheDocument();
  });

  test("falls back to the project label when the project path could not be resolved", () => {
    stubNative([{ ...COFFER_STORE, path: null }]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText("Coffer")).toBeInTheDocument();
  });

  test("clicking a row opens that store's page, addressed by type and directory", () => {
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByText("~/Coffer"));
    const [path, query] = (navigateMock.mock.calls.at(-1)?.[0] as string).split("?");
    expect(path).toBe("/agents/claude_code/memory/store");
    const params = new URLSearchParams(query);
    expect(params.get("dir")).toBe(COFFER_STORE.memory_dir);
    expect(params.get("project")).toBe(COFFER_STORE.path);
  });

  test("the tab carries no delivery action, no Coffer-memory pointer and no row actions", () => {
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    const row = screen.getByText("~/Coffer").closest("tr") as HTMLElement;
    expect(within(row).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByText(/hook/i)).toBeNull();
    expect(screen.queryByText(/memory page/i)).toBeNull();
  });

  test("no stores yet says where the agent will write them", () => {
    stubNative([]);
    render(<AgentMemoryTab agent={CODEX} />, { wrapper: wrap });
    expect(screen.getByText("No memory files from Codex yet")).toBeInTheDocument();
    expect(
      screen.getByText(/codex writes ~\/\.codex\/memories\/MEMORY\.md as it learns/i),
    ).toBeInTheDocument();
  });

  test("a failed read shows the error with a retry", () => {
    const refetch = vi.fn();
    stubNative([], { data: undefined, error: new Error("boom"), refetch });
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/couldn’t read the memory stores/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
