// frontend/src/pages/AgentDetailPage.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AgentDetailPage } from "./AgentDetailPage";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgent: vi.fn(),
  useAgents: vi.fn(() => ({ data: [] })),
  usePatchAgent: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveAgent: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  // Stubs for the (lazily-mounted) Config files + MCP surfaces.
  useAgentConfigFiles: vi.fn(() => ({ data: [], isPending: false, error: null })),
  useAgentConfigFile: vi.fn(() => ({ data: undefined, isPending: false })),
  useAgentConfigChild: vi.fn(() => ({ data: undefined, isPending: false })),
  useAgentPlugins: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
  useTogglePlugin: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUninstallPlugin: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useAgentMcpStatus: vi.fn(() => ({ data: { installed: false }, isPending: false })),
  useAgentMcpInstall: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
}));
const hooks = await import("@/lib/hooks/useAgents");
const useAgentMock = vi.mocked(hooks.useAgent);

const AGENT = {
  name: "cur",
  type: "codex" as const,
  config_dir: "/home/u/.codex",
  description: null,
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

function mockAgentLoaded() {
  useAgentMock.mockReturnValue({
    data: AGENT,
    isPending: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useAgent>);
}

function renderAt(path = "/agents/cur") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/agents/:name" element={<AgentDetailPage />} />
          <Route path="/agents" element={<div>agents list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentDetailPage header and tab routing", () => {
  test("header shows a back link, the type as a product name, and actions ordered MCP · Edit · Delete", () => {
    mockAgentLoaded();
    renderAt();
    expect(screen.getByRole("link", { name: /back to agents/i })).toHaveAttribute(
      "href",
      "/agents",
    );
    // Product name in the header chip (and again on the overview), never the key.
    expect(screen.getAllByText("Codex").length).toBeGreaterThan(0);
    expect(screen.queryByText("codex")).not.toBeInTheDocument();
    const names = screen
      .getAllByRole("button")
      .map((b) => b.textContent?.trim() ?? "")
      .filter((n) => /coffer mcp|^edit$|^delete$/i.test(n));
    expect(names).toEqual(["Install Coffer MCP", "Edit", "Delete"]);
  });

  test("?tab= opens that tab and clicking a tab writes it to the URL", () => {
    mockAgentLoaded();
    renderAt("/agents/cur?tab=plugins");
    expect(screen.getByRole("tab", { name: /^plugins$/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // Radix tabs activate on mousedown.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /config files/i }));
    expect(screen.getByRole("tab", { name: /config files/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("an unknown ?tab= falls back to the overview", () => {
    mockAgentLoaded();
    renderAt("/agents/cur?tab=nope");
    expect(screen.getByRole("tab", { name: /overview/i })).toHaveAttribute("aria-selected", "true");
  });
});

describe("AgentDetailPage", () => {
  test("renders the header, all seven workspace tabs, and the overview by default", () => {
    mockAgentLoaded();

    renderAt();

    expect(screen.getByRole("heading", { name: "cur" })).toBeInTheDocument();

    // The seven workspace tabs. Plugins is the only one that acts on the agent;
    // Memory and Conversations are read-only views of what it keeps on disk.
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^skills$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /mcp servers/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^plugins$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^memory$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /conversations/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /config files/i })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(7);

    // Categories that were never built keep their absence pinned.
    expect(screen.queryByRole("tab", { name: /subagents & commands/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /memory & rules/i })).not.toBeInTheDocument();
    // The Instructions tab was removed as redundant with Config files; master-
    // instructions delivery stays available via the API/CLI.
    expect(screen.queryByRole("tab", { name: /instructions/i })).not.toBeInTheDocument();

    // The Coffer-MCP install control lives in the header.
    expect(screen.getByRole("button", { name: /install coffer mcp/i })).toBeInTheDocument();
    // Overview (default tab) shows the config directory but no Skill directory row.
    expect(screen.getByText("/home/u/.codex")).toBeInTheDocument();
    expect(screen.queryByText(/skill directory/i)).not.toBeInTheDocument();
  });

  // `agent` declares no scope (ADR per-agent-resource-scope) — it is not a resource other agents
  // draw on, so there is no activation scope to edit. The page mounts no
  // ScopeControl at all: an agent's own enable/disable is not a header concern
  // here, so not even the control's no-scope enable/disable fallback appears.
  test("mounts no scope control for the agent", () => {
    mockAgentLoaded();
    renderAt();
    expect(screen.queryByTestId("scope-control")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /every agent/i })).not.toBeInTheDocument();
  });

  test("clicking Edit opens the edit form in a modal dialog", () => {
    mockAgentLoaded();

    renderAt();

    // No dialog until the Edit button is clicked.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /edit agent/i })).toBeInTheDocument();
  });

  test("shows a not-found message when the agent fails to load", () => {
    useAgentMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: { code: "RESOURCE_NOT_FOUND", message: "nope" },
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof hooks.useAgent>);

    renderAt();
    expect(screen.getByText(/failed to load agents/i)).toBeInTheDocument();
  });
});
