// src/components/agents/AgentOverviewTab.test.tsx — the Overview tab in each state it renders.
//
// Connected / not connected / needs repair render the Connection
// card with the one action the state calls for; config left behind and not
// found replace the whole tab with their fix card. Only the network boundary
// is faked (`fakeApi`), answering each request by path.
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentOverviewTab, type OverviewActions } from "./AgentOverviewTab";
import type { AgentOut, AgentTypeOut, CofferConnection } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";
import { fakeApi } from "@/test/fakeApi";

const callMock = fakeApi();

// Every experimental feature (memory) is on.
vi.mock("@/lib/hooks/useFeatures", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useFeatures")>()),
  useFeatureEnabled: () => true,
}));

const HOME = "/Users/me";
const AGENT: AgentOut = {
  uid: "u-cc",
  name: "claude-code",
  type: "claude_code",
  config_dir: `${HOME}/.claude`,
  display_name: "Claude Code",
  model: "claude-opus-5-5",
  tier_models: null,
  version: "2.1.281",
  install_handoff: null,
  connection_uid: null,
  state: "installed_active",
  created_at: "2026-06-12T08:00:00Z",
  updated_at: "2026-09-27T18:04:00Z",
};
const TYPE_ROW: AgentTypeOut = {
  type: "claude_code",
  name: "claude-code",
  display_name: "Claude Code",
  state: "installed_active",
  addable: false,
  config_dir: `${HOME}/.claude`,
  standard_config_dir: `${HOME}/.claude`,
  other_config_dir: null,
  default_skill_dir: `${HOME}/.claude/skills`,
  version: "2.1.281",
  install_handoff: null,
  install_url: "",
  uid: "u-cc",
};
const CONNECTED: CofferConnection = {
  state: "connected",
  parts: [{ key: "mcp", installed: true, detail: "coffer shim" }],
};
const SETTINGS = `${HOME}/.claude/settings.json`;
/** The connection with its MCP entry gone: needs repair. */
const PARTIAL: CofferConnection = {
  state: "partial",
  parts: [{ key: "mcp", installed: false, detail: null }],
};

interface World {
  connection: CofferConnection;
  /** The model the agent's own config names (the models catalogue's default). */
  nativeModel: string | null;
  transcripts: { title: string; source_path: string }[];
}
let world: World;

function route(path: string): unknown {
  const p = path.split("?")[0];
  if (p.endsWith("/coffer-connection")) return world.connection;
  if (p.endsWith("/hooks"))
    return {
      items: [
        { event: "SessionStart", path: SETTINGS },
        { event: "PreToolUse", path: SETTINGS },
      ],
      parse_errors: [],
    };
  if (p === "/skills")
    return {
      items: [
        { uid: "s1", bindings: [{ agent_uid: "u-cc" }] },
        { uid: "s2", bindings: [] },
      ],
    };
  if (p.endsWith("/unmanaged-skills")) return { items: [{ name: "a" }, { name: "b" }] };
  if (p.endsWith("/mcp-entries"))
    return {
      items: [
        { name: "coffer", is_coffer: true, matches_resource: null },
        { name: "github", is_coffer: false, matches_resource: null },
      ],
    };
  if (p.endsWith("/plugins")) return { items: [{ id: "x@m", marketplace: "m", enabled: true }] };
  if (p.endsWith("/native-memory")) return { items: [{}, {}] };
  if (p.endsWith("/transcripts"))
    return {
      total: 412,
      next_cursor: null,
      limit: 3,
      sessions: world.transcripts.map((s) => ({
        ...s,
        session_id: s.title,
        project_path: `${HOME}/WorkEnv/AI/Coffer`,
        last_activity_at: new Date(Date.now() - 5 * 3600_000).toISOString(),
        started_at: null,
        message_count: 3,
      })),
    };
  if (p.endsWith("/config-files"))
    return {
      items: [
        {
          key: "settings",
          display_name: "settings.json",
          path: SETTINGS,
          exists: true,
          kind: "file",
        },
        {
          key: "claude-md",
          display_name: "CLAUDE.md",
          path: `${HOME}/.claude/CLAUDE.md`,
          exists: false,
          kind: "file",
        },
      ],
    };
  if (p.startsWith("/agent-providers/") && p.endsWith("/models"))
    return { models: [], default_model: world.nativeModel };
  if (p === "/daemon/status") return { features: {} };
  if (p.startsWith("/resources")) return { resources: [{ uid: "m1", enabled: true, scope: null }] };
  if (p === "/providers") return { providers: [] };
  if (p === "/agents/types") return { types: [TYPE_ROW] };
  throw new Error(`unexpected request ${path}`);
}

beforeEach(() => {
  world = {
    connection: CONNECTED,
    nativeModel: "claude-opus-5-5",
    transcripts: [{ title: "Fix SeaTalk reconnect", source_path: "/s/1.jsonl" }],
  };
  callMock.mockImplementation(async (path: string) => route(path));
});
afterEach(() => vi.clearAllMocks());

function actions(): OverviewActions {
  return {
    onConnection: vi.fn(),
    onChangeConfigDir: vi.fn(),
  };
}

function renderTab(over: { agent?: Partial<AgentOut>; typeRow?: Partial<AgentTypeOut> } = {}) {
  const acts = actions();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  render(
    <AgentOverviewTab
      agent={{ ...AGENT, ...over.agent }}
      typeRow={{ ...TYPE_ROW, ...over.typeRow }}
      actions={acts}
    />,
    { wrapper: Wrapper },
  );
  return acts;
}

describe("AgentOverviewTab — connection card", () => {
  test("connected: lists the MCP entry with its file and offers no fix button", async () => {
    renderTab();
    expect(await screen.findByText(/reaches Coffer through one MCP entry/)).toBeInTheDocument();
    expect(screen.getByText("MCP entry")).toBeInTheDocument();
    expect(screen.getByText("~/.claude.json")).toBeInTheDocument();
    expect(screen.queryByText(/memory hook/i)).toBeNull();
    expect(screen.getAllByText("Current")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /Connect|Repair|Disconnect/ })).toBeNull();
  });

  test("not connected: names the files it would write and offers Connect", async () => {
    world.connection = {
      state: "disconnected",
      parts: CONNECTED.parts.map((p) => ({ ...p, installed: false, detail: null })),
    };
    const acts = renderTab();
    expect(await screen.findByText(/You review the line first/)).toBeInTheDocument();
    expect(screen.getAllByText("Not set")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(acts.onConnection).toHaveBeenCalledWith("connect");
  });

  test("needs repair: names the missing MCP entry and offers Repair (a connect)", async () => {
    world.connection = PARTIAL;
    const acts = renderTab();
    expect(await screen.findByText(/can’t reach Coffer’s tools/)).toBeInTheDocument();
    expect(screen.getByText("Missing")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Repair" }));
    expect(acts.onConnection).toHaveBeenCalledWith("connect");
  });

  acceptance("agent-registry", "the Overview offers the action the state calls for", async () => {
    const button = (n: string) => screen.queryByRole("button", { name: n });
    // Not connected: Connect.
    world.connection = {
      state: "disconnected",
      parts: CONNECTED.parts.map((p) => ({ ...p, installed: false, detail: null })),
    };
    renderTab();
    expect(await screen.findByRole("button", { name: "Connect" })).toBeInTheDocument();
    cleanup();
    // Connected: no button at all.
    world.connection = CONNECTED;
    renderTab();
    expect(await screen.findByText(/reaches Coffer through one MCP entry/)).toBeInTheDocument();
    expect(button("Connect")).toBeNull();
    expect(button("Repair")).toBeNull();
    cleanup();
    // Partial: Repair.
    world.connection = PARTIAL;
    renderTab();
    expect(await screen.findByRole("button", { name: "Repair" })).toBeInTheDocument();
  });
});

describe("AgentOverviewTab — tiles, model, details", () => {
  // Overview shows no Title or Name field, and its summary rows each open their tab.
  acceptance(
    "agent-registry",
    "the agent detail page carries six tabs and a More menu",
    async () => {
      renderTab();
      const mcp = await screen.findByRole("link", { name: /MCP servers/ });
      expect(mcp).toHaveAttribute("href", "/agents/claude_code/mcp-servers");
      expect(
        await within(mcp).findByText("1 through Coffer · 1 in .claude.json"),
      ).toBeInTheDocument();
      const skills = screen.getByRole("link", { name: /^Skills/ });
      expect(skills).toHaveAttribute("href", "/agents/claude_code/skills");
      expect(
        await within(skills).findByText("1 from Coffer · 2 not managed by Coffer"),
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^Plugins/ })).toHaveAttribute(
        "href",
        "/agents/claude_code/plugins",
      );
      const hooks = screen.getByRole("link", { name: /^Hooks/ });
      expect(hooks).toHaveAttribute("href", "/agents/claude_code/hooks");
      expect(await within(hooks).findByText("In settings.json")).toBeInTheDocument();
      expect(screen.queryByText(/^(Title|Name)$/)).not.toBeInTheDocument();
    },
  );

  test("the Model section reads provider, model and route, and Change… opens the dialog", async () => {
    renderTab();
    expect(await screen.findByText("Built-in login (Anthropic account)")).toBeInTheDocument();
    expect(screen.getByText("claude-opus-5-5")).toBeInTheDocument();
    expect(screen.queryByText("Effort")).toBeNull();
    expect(screen.getByText("Straight to Anthropic, not through Coffer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change…" }));
    expect(await screen.findByText("Change Claude Code’s model")).toBeInTheDocument();
  });

  test("on its built-in login the model is the agent's own, not a binding left from a connection", async () => {
    world.nativeModel = "gpt-6-luna";
    renderTab({ agent: { type: "codex", model: "deepseek-flash" }, typeRow: { type: "codex" } });
    expect(await screen.findByText("gpt-6-luna")).toBeInTheDocument();
    expect(screen.queryByText("deepseek-flash")).toBeNull();
  });

  test("a null model reads Built-in default", async () => {
    world.nativeModel = null;
    renderTab({ agent: { type: "codex", model: null }, typeRow: { type: "codex" } });
    expect(await screen.findByText("Default model")).toBeInTheDocument();
    expect(screen.getAllByText("Built-in default").length).toBeGreaterThan(0);
  });

  test("details carry version first, config directory, uid and registered date", async () => {
    renderTab();
    expect(await screen.findByText("v2.1.281")).toBeInTheDocument();
    expect(screen.queryByText("Type")).toBeNull();
    expect(screen.getByText(`${HOME}/.claude`)).toBeInTheDocument();
    expect(screen.getByText("u-cc")).toBeInTheDocument();
    expect(screen.getByText("12 Jun 2026")).toBeInTheDocument();
  });
});

describe("AgentOverviewTab — problem states replace the tab", () => {
  const CODEX = { type: "codex" as const, config_dir: `${HOME}/.codex` };

  test("config left behind: what is still there and the reinstall prompt", async () => {
    renderTab({
      agent: { ...CODEX, install_handoff: { prompt: "Please reinstall OpenAI Codex." } },
      typeRow: { ...CODEX, state: "config_only", standard_config_dir: `${HOME}/.codex` },
    });
    expect(screen.getByText("Install Codex")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hand off to|Copy prompt/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    // The "?" sits beside the hand-off, the only explanation of why an agent does it.
    expect(screen.getAllByRole("button", { name: "More info" })).toHaveLength(1);
    expect(document.body).not.toHaveTextContent(/npm|install -g/);
    expect(screen.queryByText("Connection")).not.toBeInTheDocument();
    expect(screen.getByText("Left in ~/.codex")).toBeInTheDocument();
    expect(screen.getByText("Last version")).toBeInTheDocument();
  });

  test("not found: reinstall, change config directory; check again re-reads", async () => {
    const acts = renderTab({ agent: CODEX, typeRow: { ...CODEX, state: "missing" } });
    expect(screen.getByText("Codex can’t be found at ~/.codex")).toBeInTheDocument();
    expect(screen.getByText("~/.codex/config.toml")).toBeInTheDocument();
    expect(screen.getByText("Last known configuration")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change config directory" }));
    expect(acts.onChangeConfigDir).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Remove from Coffer" })).toBeNull();
    await screen.findByText(/Checked at \d\d:\d\d/);
    callMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() =>
      expect(callMock).toHaveBeenCalledWith(
        "/agents/types",
        expect.objectContaining({ method: "GET" }),
      ),
    );
  });
});
