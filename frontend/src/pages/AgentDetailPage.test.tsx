// src/pages/AgentDetailPage.test.tsx — the agent page: nine path tabs, the header's action per state, a type not added.
//
// The page's collaborators are stubbed at their module boundary: the route
// (type → uid), the row actions (the dialogs and menu the list shares), the
// counts, and each tab — every tab has its own test next to it.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import "@/i18n";
import { acceptance } from "@/test/acceptance";
import type { AgentRowState } from "@/lib/agents/rowState";
import { AgentDetailPage } from "./AgentDetailPage";

vi.mock("@/lib/hooks/useAgentRoute", () => ({ useAgentRoute: vi.fn() }));
vi.mock("@/lib/hooks/useAgentCounts", () => ({
  useAgentCounts: vi.fn(() => ({
    skills: { coffer: 12, own: 4 },
    mcp: { coffer: 5, own: 3, duplicates: 1 },
    plugins: { total: 3, enabled: 2, marketplaces: 2 },
    hooks: { total: 7, coffer: 1, files: 3 },
    sessions: 412,
  })),
}));
const { change, enable, stub } = vi.hoisted(() => ({
  change: vi.fn(),
  enable: vi.fn(),
  stub: (name: string) => () => <div data-testid="tab-body">{name}</div>,
}));
vi.mock("@/lib/hooks/useAgents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useAgents")>()),
  useAgentHooks: () => ({ data: undefined, refetch: vi.fn(), isFetching: false }),
  useAgentConnection: () => ({ data: undefined }),
}));
vi.mock("@/components/agents/list/useAgentRowActions", () => ({ useAgentRowActions: vi.fn() }));

vi.mock("@/components/agents/AgentOverviewTab", () => ({ AgentOverviewTab: stub("overview") }));
vi.mock("@/components/agents/model/AgentModelTab", () => ({ AgentModelTab: stub("model") }));
vi.mock("@/components/agents/AgentSkillsTab", () => ({ AgentSkillsTab: stub("skills") }));
vi.mock("@/components/agents/AgentMcpServersTab", () => ({ AgentMcpServersTab: stub("mcp") }));
vi.mock("@/components/agents/AgentPluginsTab", () => ({ AgentPluginsTab: stub("plugins") }));
vi.mock("@/components/agents/AgentHooksTab", () => ({ AgentHooksTab: stub("hooks") }));
vi.mock("@/components/agents/AgentConfigFilesTab", () => ({ AgentConfigFilesTab: stub("config") }));
vi.mock("@/components/agents/AgentMemoryTab", () => ({ AgentMemoryTab: stub("memory") }));
vi.mock("@/components/agents/sessions/AgentSessionsTab", () => ({
  AgentSessionsTab: stub("sessions"),
}));

const routeMod = await import("@/lib/hooks/useAgentRoute");
const actionsMod = await import("@/components/agents/list/useAgentRowActions");

const TYPE_ROW = {
  type: "claude_code" as const,
  uid: "agt_cc",
  name: "claude-code",
  display_name: "Claude Code",
  state: "installed_active" as const,
  addable: false,
  config_dir: "/Users/u/.claude",
  standard_config_dir: "/Users/u/.claude",
  other_config_dir: null,
  default_skill_dir: "/Users/u/.claude/skills",
  version: "2.1.281",
};
const AGENT = {
  uid: "agt_cc",
  type: "claude_code" as const,
  name: "claude-code",
  display_name: "Claude Code",
  config_dir: "/Users/u/.claude",
  model: "claude-opus-5-5",
  effort: null,
  tier_models: null,
  wire_api: null,
  state: "installed_active" as const,
  version: "2.1.281",
  created_at: "2026-06-12T00:00:00Z",
  updated_at: "2026-06-12T00:00:00Z",
};

function mockRoute(opts: { added?: boolean; rowState?: AgentRowState; typeRow?: object } = {}) {
  const added = opts.added ?? true;
  const typeRow = { ...TYPE_ROW, uid: added ? "agt_cc" : null, ...opts.typeRow };
  vi.mocked(routeMod.useAgentRoute).mockReturnValue({
    type: "claude_code",
    typeRow,
    uid: added ? "agt_cc" : "",
    agent: added ? AGENT : undefined,
    isPending: false,
    error: null,
    notAdded: !added,
    redirecting: false,
  } as unknown as ReturnType<typeof routeMod.useAgentRoute>);
  vi.mocked(actionsMod.useAgentRowActions).mockReturnValue({
    state: opts.rowState ?? "connected",
    actions: [{ key: "disconnect", label: "Disconnect", onSelect: () => change("disconnect") }],
    primary: null,
    dialogs: null,
    open: { change, enable, configDir: vi.fn(), remove: vi.fn() },
  } as unknown as ReturnType<typeof actionsMod.useAgentRowActions>);
}

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function renderAt(path = "/agents/claude_code") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/agents/:type" element={<AgentDetailPage />} />
        <Route path="/agents/:type/:tab" element={<AgentDetailPage />} />
      </Routes>
      <Where />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentDetailPage", () => {
  // Scenario (revise-web-ui-ia, agent-registry): "the agent detail page carries nine tabs"
  test("nine tabs in order, each at its own path, the list tabs with their counts", () => {
    mockRoute();
    renderAt("/agents/claude_code/skills");
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual([
      "Overview",
      "Model",
      "Skills16",
      "MCP servers8",
      "Plugins3",
      "Hooks7",
      "Config files",
      "Memory",
      "Sessions412",
    ]);
    expect(screen.getByRole("tab", { name: /Skills/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("tab-body")).toHaveTextContent("skills");
    // Radix activates a tab on mousedown.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Hooks/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/agents/claude_code/hooks");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Overview" }));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/agents\/claude_code$/);
  });

  test("the header names the agent by its type, with its fixed name, version, directory and model", () => {
    mockRoute();
    renderAt();
    expect(screen.getByRole("heading", { name: /Claude Code/ })).toBeInTheDocument();
    expect(
      screen.getByText("claude-code · v2.1.281 · ~/.claude · claude-opus-5-5"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Agents/ })).toHaveAttribute("href", "/agents");
  });

  acceptance("agent-registry", "the header offers the action the state calls for", () => {
    mockRoute({ rowState: "not_connected" });
    const { unmount } = renderAt();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Connect to Coffer" }));
    expect(change).toHaveBeenCalledWith("connect");
    unmount();

    // Connected: Disconnect from Coffer is in the header's ⋯ menu (it opens a
    // preview of what it removes before anything is written).
    mockRoute({ rowState: "connected" });
    const connected = renderAt();
    expect(screen.getByText("Connected to Coffer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect to Coffer" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Claude Code" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Disconnect" }));
    expect(change).toHaveBeenCalledWith("disconnect");
    connected.unmount();

    // Partial: reads Needs repair and offers Repair (which puts the rest back).
    mockRoute({ rowState: "needs_repair" });
    renderAt();
    expect(screen.getByText("Needs repair")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Repair" })).toBeInTheDocument();
  });

  test("a disabled agent offers Enable", () => {
    mockRoute({ rowState: "disabled" });
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: "Enable" }));
    expect(enable).toHaveBeenCalled();
  });

  test("a type not added yet shows the header and Add, and no tabs", () => {
    mockRoute({ added: false, rowState: "not_added", typeRow: { addable: true } });
    renderAt("/agents/claude_code");
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.getByText("Claude Code isn’t added yet")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Add" })[0]);
    expect(change).toHaveBeenCalledWith("add");
  });

  test("a type that is not installed says how to install it", () => {
    mockRoute({
      added: false,
      rowState: "not_installed",
      typeRow: { state: "missing", version: null },
    });
    renderAt();
    expect(screen.getByText("Claude Code isn’t installed")).toBeInTheDocument();
    expect(screen.getByText(/npm install -g @anthropic-ai\/claude-code/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy command" })).toBeInTheDocument();
  });
});
