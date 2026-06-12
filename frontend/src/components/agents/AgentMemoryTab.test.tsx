// frontend/src/components/agents/AgentMemoryTab.test.tsx
//
// The "Memory" tab on the agent detail page renders memory stores as a compact
// DataTable (like the Skills/MCP tabs): each row shows scope + projection state
// and a projection Switch; clicking a row navigates to the store's detail page
// (/memory/:name) while flipping the Switch toggles projection WITHOUT
// navigating. We mock the projection hooks so the component renders
// deterministically and assert the table + establish/remove wiring.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentMemoryTab } from "./AgentMemoryTab";
import type { AgentOut } from "@/lib/api/agents";

const establishMutate = vi.fn();
const removeMutate = vi.fn();
const navigateMock = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

vi.mock("@/lib/hooks/useMemoryProjections", () => ({
  useMemoryStores: vi.fn(),
  useMemoryProjections: vi.fn(),
  useEstablishProjection: vi.fn(() => ({ mutate: establishMutate, isPending: false, error: null })),
  useRemoveProjection: vi.fn(() => ({ mutate: removeMutate, isPending: false, error: null })),
}));
const hooks = await import("@/lib/hooks/useMemoryProjections");

// The native-memory discovery banner: default to "nothing unmanaged".
vi.mock("@/lib/api/nativeMemory", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/nativeMemory")>()),
  getAgentNativeMemory: vi.fn(async () => ({ projects: [], unmanaged_fact_count: 0 })),
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

const STORE = {
  ref: "memory:global",
  kind: "memory",
  name: "global",
  scope: "global" as const,
  project_id: "0".repeat(26),
  description: null,
  config: { retrieval_modes: ["grep", "keyword"], default_mode: "keyword", max_fact_chars: 8192 },
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

const PROJECT_STORE = {
  ...STORE,
  ref: "memory:project-x",
  name: "project-x",
  scope: "project" as const,
  project_id: "01HXYZPROJECTULID0000000000",
  project_root: "/home/u/code/project-x",
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
  test("renders a store row and shows 'not projected' when no projection exists", () => {
    stubStores();
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByRole("row", { name: /global/i })).toBeInTheDocument();
    expect(screen.getByText(/not projected/i)).toBeInTheDocument();
    expect(screen.getByRole("switch")).not.toBeChecked();
  });

  test("clicking a store row navigates to its memory detail page", () => {
    stubStores();
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("row", { name: /global/i }));
    expect(navigateMock).toHaveBeenCalledWith("/memory/global", {
      state: { backTo: "/agents/claude", backLabel: "claude" },
    });
  });

  test("toggling the projection Switch establishes a projection WITHOUT navigating", () => {
    stubStores();
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("switch"));
    expect(establishMutate).toHaveBeenCalledWith({ agentRef: "claude" });
    // Flipping the switch must not trigger the row's navigate-to-detail click.
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("shows projection mode/target and toggling off removes it", () => {
    stubStores();
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [
        {
          agent_ref: "claude",
          projection_mode: "SYMLINK",
          target_path: "/home/u/.claude/projects/x/memory",
          native_memory_disabled: false,
        },
      ],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText("SYMLINK")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.claude/projects/x/memory")).toBeInTheDocument();

    const sw = screen.getByRole("switch");
    expect(sw).toBeChecked();
    fireEvent.click(sw);
    expect(removeMutate).toHaveBeenCalledWith("claude");
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("project-scoped store passes its project_root when establishing", () => {
    stubStores([PROJECT_STORE]);
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("switch"));
    expect(establishMutate).toHaveBeenCalledWith({
      agentRef: "claude",
      projectRoot: "/home/u/code/project-x",
    });
  });

  test("project store with no known root disables the toggle and does not establish", () => {
    stubStores([{ ...PROJECT_STORE, project_root: null }]);
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    const sw = screen.getByRole("switch");
    expect(sw).toBeDisabled();
    fireEvent.click(sw);
    expect(establishMutate).not.toHaveBeenCalled();
    expect(screen.getAllByText(/no known root/i).length).toBeGreaterThanOrEqual(1);
  });
});
