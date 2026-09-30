// src/components/agents/AgentOverviewTab.test.tsx — the Overview tab in each state it renders.
//
// Connected / not connected / needs repair / disabled render the Connection
// card with the one action the state calls for; config left behind and not
// found replace the whole tab with their fix card. Only the network boundary
// is mocked: `call` (every hand-written request) and the generated client
// (the resource reads), each answering by path.
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentOverviewTab, type OverviewActions } from "./AgentOverviewTab";
import type { AgentOut, AgentTypeOut, CofferConnection, CofferHook } from "@/lib/api/agents";
import { mockApiClient } from "@/test/mockApiClient";

vi.mock("@/lib/api/call", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/call")>()),
  call: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { call } = await import("@/lib/api/call");
const { getApiClient } = await import("@/lib/api/client");
const callMock = vi.mocked(call);

const HOME = "/Users/me";
const AGENT: AgentOut = {
  uid: "u-cc",
  name: "claude-code",
  type: "claude_code",
  config_dir: `${HOME}/.claude`,
  display_name: "Claude Code",
  model: "claude-opus-5-5",
  effort: "high",
  tier_models: null,
  wire_api: null,
  version: "2.1.281",
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
  uid: "u-cc",
};
const HOOK: CofferHook = {
  event: "SessionStart",
  path: `${HOME}/.claude/settings.json`,
  health: "current",
  trust: "not_required",
  installed_command: 'coffer memory hook --agent-uid u-cc --cwd "$PWD"',
  expected_command: 'coffer memory hook --agent-uid u-cc --cwd "$PWD"',
  last_fired_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
};
const CONNECTED: CofferConnection = {
  state: "connected",
  parts: [
    { key: "mcp", installed: true, detail: "coffer shim" },
    {
      key: "memory_hook",
      installed: true,
      detail: 'coffer memory hook --agent-uid u-cc --cwd "$PWD"',
    },
  ],
};

interface World {
  connection: CofferConnection;
  hook: CofferHook | null;
  enabled: boolean;
  transcripts: { title: string; source_path: string }[];
}
let world: World;

function route(path: string): unknown {
  const p = path.split("?")[0];
  if (p.endsWith("/coffer-connection")) return world.connection;
  if (p.endsWith("/hooks"))
    return {
      coffer_hook: world.hook,
      items: [
        { event: "SessionStart", path: HOOK.path, coffer: true },
        { event: "PreToolUse", path: HOOK.path, coffer: false },
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
          path: HOOK.path,
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
  if (p === "/providers") return { providers: [] };
  if (p === "/agents/types") return { types: [TYPE_ROW] };
  throw new Error(`unexpected request ${path}`);
}

beforeEach(() => {
  world = {
    connection: CONNECTED,
    hook: HOOK,
    enabled: true,
    transcripts: [{ title: "Fix SeaTalk reconnect", source_path: "/s/1.jsonl" }],
  };
  callMock.mockImplementation(async (path: string) => route(path) as never);
  const api = mockApiClient({
    GET: vi.fn(async (path: string) =>
      path === "/resources/{uid}"
        ? { data: { uid: "u-cc", enabled: world.enabled }, error: undefined }
        : { data: { resources: [{ uid: "m1", enabled: true, scope: null }] }, error: undefined },
    ),
  });
  vi.mocked(getApiClient).mockReturnValue(api as never);
});
afterEach(() => vi.clearAllMocks());

function actions(): OverviewActions {
  return {
    onConnection: vi.fn(),
    onEnable: vi.fn(),
    onChangeConfigDir: vi.fn(),
    onRemove: vi.fn(),
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
  test("connected: says so, lists both parts with their files, offers Disconnect", async () => {
    const acts = renderTab();
    expect(await screen.findByText("Connected to Coffer")).toBeInTheDocument();
    expect(screen.getByText("MCP entry")).toBeInTheDocument();
    expect(screen.getByText("~/.claude.json")).toBeInTheDocument();
    expect(screen.getByText("Memory hook")).toBeInTheDocument();
    expect(screen.getByText(/last fired 2h ago/)).toBeInTheDocument();
    expect(screen.getAllByText("Current")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(acts.onConnection).toHaveBeenCalledWith("disconnect");
  });

  test("not connected: names the files it would write and offers Connect to Coffer", async () => {
    world.connection = {
      state: "disconnected",
      parts: CONNECTED.parts.map((p) => ({ ...p, installed: false, detail: null })),
    };
    const acts = renderTab();
    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(screen.getByText(/You review the exact lines/)).toBeInTheDocument();
    expect(screen.getAllByText("Missing")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Connect to Coffer" }));
    expect(acts.onConnection).toHaveBeenCalledWith("connect");
  });

  test("needs repair: names the out-of-date hook and offers Repair (a connect)", async () => {
    world.connection = { ...CONNECTED, state: "partial" };
    world.hook = { ...HOOK, health: "stale" };
    const acts = renderTab();
    expect(await screen.findByText("Needs repair")).toBeInTheDocument();
    expect(screen.getByText(/runs a command this Coffer no longer accepts/)).toBeInTheDocument();
    expect(screen.getByText("Out of date")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Repair" }));
    expect(acts.onConnection).toHaveBeenCalledWith("connect");
  });

  test("disabled: parts read Idle, MCP and Skills serve nothing, offers Enable", async () => {
    world.enabled = false;
    const acts = renderTab();
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
    expect(screen.getAllByText("Idle")).toHaveLength(2);
    expect(await screen.findAllByText(/None while disabled/)).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Enable" }));
    expect(acts.onEnable).toHaveBeenCalled();
  });

  test("the memory hook row appears only when the connection lists that part", async () => {
    world.connection = { state: "connected", parts: [CONNECTED.parts[0]] };
    renderTab();
    expect(await screen.findByText("Connected to Coffer")).toBeInTheDocument();
    expect(screen.queryByText("Memory hook")).not.toBeInTheDocument();
  });
});

describe("AgentOverviewTab — summary, model, details, sessions", () => {
  // Scenario (revise-web-ui-ia, agent-registry): "the agent detail page carries nine tabs"
  // — Overview shows no Title or Name field, and its summary rows each open their tab.
  test("summary rows count Coffer's and the agent's own, each opening its tab; no Title/Name", async () => {
    renderTab();
    const mcp = await screen.findByRole("link", { name: /MCP servers/ });
    expect(mcp).toHaveAttribute("href", "/agents/claude_code/mcp-servers");
    expect(
      await within(mcp).findByText("1 through Coffer · 1 directly in .claude.json"),
    ).toBeInTheDocument();
    expect(within(mcp).getByText("1 to review")).toBeInTheDocument();
    const skills = screen.getByRole("link", { name: /^Skills/ });
    expect(skills).toHaveAttribute("href", "/agents/claude_code/skills");
    expect(
      await within(skills).findByText(
        "1 delivered by Coffer · 2 on disk that Coffer doesn’t manage",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Plugins/ })).toHaveAttribute(
      "href",
      "/agents/claude_code/plugins",
    );
    const hooks = screen.getByRole("link", { name: /^Hooks/ });
    expect(hooks).toHaveAttribute("href", "/agents/claude_code/hooks");
    expect(
      await within(hooks).findByText("2 hooks in settings.json · 1 is Coffer’s"),
    ).toBeInTheDocument();
    expect(await screen.findByText("settings.json")).toBeInTheDocument();
    expect(screen.queryByText(/^(Title|Name)$/)).not.toBeInTheDocument();
  });

  test("the Model block reads provider, model and effort, and links to the Model tab", async () => {
    renderTab();
    expect(await screen.findByText("Built-in login (Anthropic account)")).toBeInTheDocument();
    expect(screen.getByText("claude-opus-5-5")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Change" })).toHaveAttribute(
      "href",
      "/agents/claude_code/model",
    );
  });

  test("Codex says Effort too, and a null effort reads Model default", async () => {
    renderTab({ agent: { type: "codex", effort: null }, typeRow: { type: "codex" } });
    expect(await screen.findByText("Effort")).toBeInTheDocument();
    expect(screen.getByText("Model default")).toBeInTheDocument();
  });

  test("details carry type, config directory, uid and registered date", async () => {
    renderTab();
    expect(await screen.findByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText(`${HOME}/.claude`)).toBeInTheDocument();
    expect(screen.getByText("u-cc")).toBeInTheDocument();
    expect(screen.getByText("2026-06-12")).toBeInTheDocument();
  });

  test("recent sessions open the session in the Sessions tab; All N opens the tab", async () => {
    renderTab();
    const row = await screen.findByRole("link", { name: /Fix SeaTalk reconnect/ });
    expect(row).toHaveAttribute("href", "/agents/claude_code/sessions?session=%2Fs%2F1.jsonl");
    expect(within(row).getByText("5h")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All 412" })).toHaveAttribute(
      "href",
      "/agents/claude_code/sessions",
    );
  });

  test("recent sessions are hidden when there are none", async () => {
    world.transcripts = [];
    renderTab();
    expect(await screen.findByText("Connected to Coffer")).toBeInTheDocument();
    expect(screen.queryByText("Recent sessions")).not.toBeInTheDocument();
  });
});

describe("AgentOverviewTab — problem states replace the tab", () => {
  const CODEX = { type: "codex" as const, config_dir: `${HOME}/.codex` };

  test("config left behind: what is still there and the install command", async () => {
    const acts = renderTab({
      agent: CODEX,
      typeRow: { ...CODEX, state: "config_only", standard_config_dir: `${HOME}/.codex` },
    });
    expect(
      screen.getByText("Codex’s config is left behind — the program isn’t installed"),
    ).toBeInTheDocument();
    expect(screen.getByText("npm install -g @openai/codex")).toBeInTheDocument();
    expect(screen.queryByText("Connection")).not.toBeInTheDocument();
    expect(screen.getByText("Left in ~/.codex")).toBeInTheDocument();
    // Revealing the folder and removing the agent stay in the ⋯ menu.
    expect(screen.queryByRole("button", { name: "Remove from list" })).not.toBeInTheDocument();
    expect(acts.onRemove).not.toHaveBeenCalled();
  });

  test("not found: reinstall, change config directory, remove from Coffer; check again re-reads", async () => {
    const acts = renderTab({ agent: CODEX, typeRow: { ...CODEX, state: "missing" } });
    expect(screen.getByText("Codex can’t be found at ~/.codex")).toBeInTheDocument();
    expect(screen.getByText("~/.codex/config.toml")).toBeInTheDocument();
    expect(screen.getByText("Last known configuration")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change config directory" }));
    expect(acts.onChangeConfigDir).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove from Coffer" }));
    expect(acts.onRemove).toHaveBeenCalled();
    await screen.findByText(/Checked at \d\d:\d\d/);
    callMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(callMock).toHaveBeenCalledWith("/agents/types");
  });
});
