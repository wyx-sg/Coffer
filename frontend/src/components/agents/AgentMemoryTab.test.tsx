// frontend/src/components/agents/AgentMemoryTab.test.tsx
//
// The "Memory" tab on the agent detail page renders memory stores as a compact
// READ-ONLY DataTable (like the read-only MCP-servers list): each row shows the
// store's readable name, scope, and fact count; clicking a row navigates to the
// store's detail page (/memory/:name). The tab no longer projects a store into
// the agent's native memory, so there are no projection toggles or takeover
// banner. We mock useMemoryStores so the component renders deterministically.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentMemoryTab } from "./AgentMemoryTab";
import type { AgentOut } from "@/lib/api/agents";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

vi.mock("@/lib/hooks/useMemoryStores", () => ({
  useMemoryStores: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useMemoryStores");

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

const STORE = {
  ref: "memory:global",
  kind: "memory",
  name: "global",
  scope: "global" as const,
  project_id: "0".repeat(26),
  description: null,
  config: { retrieval_modes: ["grep", "keyword"], default_mode: "keyword", max_fact_chars: 8192 },
  enabled: true,
  fact_count: 3,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

const PROJECT_STORE = {
  ...STORE,
  ref: "memory:project-x",
  name: "project-01HXYZPROJECTULID0000000000",
  scope: "project" as const,
  project_id: "01HXYZPROJECTULID0000000000",
  project_root: "/home/u/code/project-x",
  fact_count: 7,
};

function stubStores(stores: unknown[] = [STORE]) {
  vi.mocked(hooks.useMemoryStores).mockReturnValue({
    data: stores,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useMemoryStores>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentMemoryTab", () => {
  test("shows the access-via-gateway note (read-only access)", () => {
    stubStores();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/accesses coffer memory via the mcp gateway/i)).toBeInTheDocument();
  });

  test("renders the store list with readable names and fact counts", () => {
    stubStores([STORE, PROJECT_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });

    // Global store reads as "global"; the per-project store reads as its
    // directory basename, not the opaque project-<ULID> name.
    expect(screen.getByRole("row", { name: /global/i })).toBeInTheDocument();
    expect(screen.getByText("project-x")).toBeInTheDocument();
    expect(screen.getByText("/home/u/code/project-x")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  test("clicking a store row navigates to its memory detail page with back-state", () => {
    stubStores();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("row", { name: /global/i }));
    expect(navigateMock).toHaveBeenCalledWith("/memory/global", {
      state: { backTo: "/agents/claude", backLabel: "claude" },
    });
  });

  test("renders no projection toggles or takeover controls", () => {
    stubStores([STORE, PROJECT_STORE]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByText(/take over/i)).not.toBeInTheDocument();
  });

  test("shows the empty message when there are no stores", () => {
    stubStores([]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText(/no memory stores yet/i)).toBeInTheDocument();
  });
});
