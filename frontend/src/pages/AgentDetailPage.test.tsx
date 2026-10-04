// src/pages/AgentDetailPage.test.tsx — the agent page: eight path tabs behind a More overflow, the header's action per state, a type not added.
//
// The page's collaborators are stubbed at their module boundary: the route
// (type → uid), the row actions (the dialogs and menu the list shares), the
// counts, and each tab — every tab has its own test next to it.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import "@/i18n";
import { acceptance } from "@/test/acceptance";
import type { AgentRowState } from "@/lib/agents/rowState";
import { AgentDetailPage } from "./AgentDetailPage";

vi.mock("@/lib/hooks/useAgentRoute", () => ({ useAgentRoute: vi.fn() }));
const { change, enable, stub } = vi.hoisted(() => ({
  change: vi.fn(),
  enable: vi.fn(),
  stub: (name: string) => () => <div data-testid="tab-body">{name}</div>,
}));
vi.mock("@/lib/hooks/useAgents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useAgents")>()),
  useAgentHooks: () => ({ data: undefined, refetch: vi.fn(), isFetching: false }),
  useAgentConnection: () => ({ data: undefined }),
  useAgent: () => ({ data: undefined }),
  useAgentPlugins: () => ({ data: pluginsData }),
}));
let pluginsData: { items: { cache_present: boolean }[] } | undefined;
// Rotate proxy token is in ⋯ only while the agent routes through Coffer's proxy.
let rotateAction: { key: string; label: string; onSelect: () => void } | null = null;
vi.mock("@/components/agents/detail/useRotateProxyToken", () => ({
  useRotateProxyAction: () => rotateAction,
}));
vi.mock("@/components/agents/list/useAgentRowActions", () => ({ useAgentRowActions: vi.fn() }));
vi.mock("@/lib/hooks/useFeatures", () => ({ useFeatureEnabled: () => true }));
// No managed agent to ask: a hand-off offers Copy prompt only.
vi.mock("@/lib/hooks/useAgentProviders", () => ({ useAgentProviders: () => ({ data: [] }) }));

vi.mock("@/components/agents/AgentOverviewTab", () => ({ AgentOverviewTab: stub("overview") }));
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
  } as unknown as ReturnType<typeof routeMod.useAgentRoute>);
  vi.mocked(actionsMod.useAgentRowActions).mockReturnValue({
    state: opts.rowState ?? "connected",
    actions: [{ key: "copy-uid", label: "Copy uid", onSelect: vi.fn() }],
    primary: null,
    dialogs: null,
    open: { change, enable, configDir: vi.fn() },
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

afterEach(() => {
  vi.clearAllMocks();
  pluginsData = undefined;
  rotateAction = null;
});

describe("AgentDetailPage", () => {
  // Tabs and paths here; Overview's summary rows and Config files' instructions
  // file are asserted under the same scenario in their own tab tests.
  acceptance("agent-registry", "the agent detail page carries six tabs and a More menu", () => {
    mockRoute();
    renderAt("/agents/claude_code/skills");
    // Six in the strip, no counts, and no Model tab; Plugins and Memory sit behind More.
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual([
      "Overview",
      "Skills",
      "MCP servers",
      "Hooks",
      "Config files",
      "Sessions",
    ]);
    expect(screen.getByRole("button", { name: "More" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Skills/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("tab-body")).toHaveTextContent("skills");
    // Radix activates a tab on mousedown.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Hooks/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/agents/claude_code/hooks");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Overview" }));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/agents\/claude_code$/);
  });

  test("an open tab inside More gives More its name; a hidden tab that needs you adds a dot", () => {
    mockRoute();
    renderAt("/agents/claude_code");
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    const items = within(screen.getByRole("menu")).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual(["Plugins", "Memory"]);
    fireEvent.click(items[1]);
    expect(screen.getByTestId("where")).toHaveTextContent("/agents/claude_code/memory");
    expect(screen.getByRole("button", { name: "Memory" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
  });

  test("a plugin whose files are gone puts a warning dot on More", () => {
    pluginsData = { items: [{ cache_present: false }] };
    mockRoute();
    const { container } = renderAt("/agents/claude_code");
    expect(container.querySelector("button[aria-haspopup='menu'] .bg-warning")).not.toBeNull();
  });

  test("the removed Model address opens Overview", () => {
    mockRoute();
    renderAt("/agents/claude_code/model");
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/agents\/claude_code$/);
    expect(screen.getByTestId("tab-body")).toHaveTextContent("overview");
  });

  test("the header names the agent by its type and carries no detail line", () => {
    mockRoute();
    renderAt();
    expect(screen.getByRole("heading", { name: /Claude Code/ })).toBeInTheDocument();
    expect(screen.queryByText(/v2\.1\.281/)).not.toBeInTheDocument();
  });

  acceptance("agent-registry", "the header carries one status pill and a fixed action pair", () => {
    // The header never turns into a fix button: Connect, Repair and Turn on are the Overview's.
    for (const [rowState, word] of [
      ["not_connected", "Not connected"],
      ["connected", "Connected"],
      ["needs_repair", "Needs repair"],
      ["disabled", "Off"],
    ] as const) {
      mockRoute({ rowState });
      const { unmount } = renderAt();
      expect(screen.getByText(word)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "New conversation" })).toBeInTheDocument();
      for (const name of ["Connect", "Repair", "Turn on", "Check again"]) {
        expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
      }
      unmount();
    }
  });

  test("an agent left behind has ⋯ only", () => {
    mockRoute({ rowState: "config_left_behind", typeRow: { state: "config_only" } });
    renderAt();
    expect(screen.getByText("Config left behind")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New conversation" })).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "More actions for Claude Code" }),
    ).toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "Rotate proxy token is offered only while the agent routes through the proxy",
    () => {
      mockRoute({ rowState: "connected" });
      const first = renderAt();
      fireEvent.click(screen.getByRole("button", { name: "More actions for Claude Code" }));
      expect(
        screen.queryByRole("menuitem", { name: "Rotate proxy token" }),
      ).not.toBeInTheDocument();
      first.unmount();

      const onSelect = vi.fn();
      rotateAction = { key: "rotate-token", label: "Rotate proxy token", onSelect };
      renderAt();
      fireEvent.click(screen.getByRole("button", { name: "More actions for Claude Code" }));
      fireEvent.click(screen.getByRole("menuitem", { name: "Rotate proxy token" }));
      expect(onSelect).toHaveBeenCalled();
    },
  );

  test("a type not added yet shows the header and Connect, and no tabs", () => {
    mockRoute({ added: false, rowState: "not_added", typeRow: { addable: true } });
    renderAt("/agents/claude_code");
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.getByText("Claude Code isn’t connected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(change).toHaveBeenCalledWith("add");
  });

  test("a type that is not installed offers the daemon's install prompt", () => {
    mockRoute({
      added: false,
      rowState: "not_installed",
      typeRow: {
        state: "missing",
        version: null,
        install_handoff: { prompt: "Please install Claude Code on this machine." },
      },
    });
    renderAt();
    expect(screen.getByText("Claude Code isn’t installed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/npm|install -g/);
  });
});
