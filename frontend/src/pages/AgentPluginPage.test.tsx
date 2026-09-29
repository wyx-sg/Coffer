// src/pages/AgentPluginPage.test.tsx — one installed plugin's page, opened from the agent's Plugins tab.
//
// One installed plugin's page, reached from the agent's Plugins tab: the
// manifest metadata, the marketplace and its source, the install directory with
// open / reveal, and the components the plugin contributes. The header carries
// the enabled switch and Uninstall; the back link and a successful uninstall
// both return to the Plugins tab.
//
// The agent API is mocked at the network boundary (the real hooks run), as are
// the fs actions (their own suite covers the transport). The page is addressed
// by the agent's type and reads its uid from the type listing; the uid is not
// the type, and the plugin id carries an `@`, so the route has to decode it.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentPluginPage } from "./AgentPluginPage";
import type { AgentOut, AgentTypeOut, PluginDetailOut } from "@/lib/api/agents";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    types: vi.fn(),
    get: vi.fn(),
    plugin: vi.fn(),
    togglePlugin: vi.fn(),
    uninstallPlugin: vi.fn(),
  },
}));

const openMock = vi.fn(() => Promise.resolve());
const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: revealMock }),
}));

const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const UID = "u-claude";
const TYPE = "claude_code";
const TAB = `/agents/${TYPE}/plugins`;

const TYPE_ROW: AgentTypeOut = {
  type: TYPE,
  name: "claude_code",
  display_name: "Claude Code",
  addable: false,
  config_dir: "/home/u/.claude",
  standard_config_dir: "/home/u/.claude",
  other_config_dir: null,
  default_skill_dir: "/home/u/.claude/skills",
  state: "installed_active",
  uid: UID,
  version: null,
};

const AGENT: AgentOut = {
  uid: UID,
  name: TYPE,
  type: TYPE,
  config_dir: "/home/u/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  wire_api: null,
  version: null,
  state: "installed_active",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};
const ID = "hud@claude-hud";
const INSTALL = "/home/u/.claude/plugins/cache/claude-hud/hud/0.2.0";

const DETAIL: PluginDetailOut = {
  plugin: {
    id: ID,
    name: "hud",
    marketplace: "claude-hud",
    enabled: true,
    cache_present: true,
    version: "0.2.0",
    description: "Real-time status line",
    author: "Jarrod",
    homepage: "https://example.com/hud",
    skills: ["setup-hud"],
    commands: ["configure"],
    mcp_servers: [],
  },
  marketplace_source_type: "github",
  marketplace_source: "jarrodwatts/claude-hud",
  install_path: INSTALL,
  can_uninstall: true,
  skills: [{ name: "setup-hud", description: "Install the status line" }],
  commands: [{ name: "configure", description: null }],
  agents: [{ name: "hud-reviewer", description: "Reviews the HUD" }],
  hooks: ["SessionStart"],
  mcp_servers: ["hud-srv"],
};

function Landed() {
  const loc = useLocation();
  return <div data-testid="landed">{`${loc.pathname}${loc.search}`}</div>;
}

function renderPage(detail: PluginDetailOut | Error = DETAIL) {
  api.types.mockResolvedValue({ types: [TYPE_ROW] });
  api.get.mockResolvedValue(AGENT);
  if (detail instanceof Error) api.plugin.mockRejectedValue(detail);
  else api.plugin.mockResolvedValue(detail);
  api.togglePlugin.mockResolvedValue(undefined);
  api.uninstallPlugin.mockResolvedValue(undefined);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`${TAB}/${encodeURIComponent(ID)}`]}>
        <Routes>
          <Route path="/agents/:type/plugins/:pluginId" element={<AgentPluginPage />} />
          <Route path="/agents/:type/plugins" element={<Landed />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentPluginPage", () => {
  acceptance("agent-registry", "open a plugin's detail page from the Plugins tab", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "hud" })).toBeInTheDocument();
    // The encoded id reached the API decoded, addressed to the uid the type resolved to.
    expect(api.plugin).toHaveBeenCalledWith(UID, ID);

    // Metadata and where it came from.
    expect(screen.getByText("Real-time status line")).toBeInTheDocument();
    expect(screen.getByText("0.2.0")).toBeInTheDocument();
    expect(screen.getByText("Jarrod")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://example.com/hud" })).toBeInTheDocument();
    expect(screen.getByText("(jarrodwatts/claude-hud)")).toBeInTheDocument();
    expect(screen.getByText(INSTALL)).toBeInTheDocument();

    // Everything the package contributes, with descriptions where it has them.
    expect(screen.getByText("setup-hud")).toBeInTheDocument();
    expect(screen.getByText("Install the status line")).toBeInTheDocument();
    expect(screen.getByText("configure")).toBeInTheDocument();
    expect(screen.getByText("hud-reviewer")).toBeInTheDocument();
    expect(screen.getByText("Reviews the HUD")).toBeInTheDocument();
    expect(screen.getByText("SessionStart")).toBeInTheDocument();
    expect(screen.getByText("hud-srv")).toBeInTheDocument();

    // Back returns to the agent's Plugins tab.
    fireEvent.click(screen.getByRole("link", { name: /back to plugins/i }));
    expect(await screen.findByTestId("landed")).toHaveTextContent(TAB);
  });

  test("reveal opens the install directory in the file manager", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: en.fileActions.reveal }));
    await waitFor(() => expect(revealMock).toHaveBeenCalledWith(INSTALL));
  });

  test("the enabled switch toggles the plugin", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("switch", { name: /enabled: hud/i }));
    await waitFor(() => expect(api.togglePlugin).toHaveBeenCalledWith(UID, ID, false));
  });

  test("uninstall confirms, calls the API and returns to the Plugins tab", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /uninstall/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(`claude plugin uninstall ${ID}`)).toBeInTheDocument();
    expect(api.uninstallPlugin).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /uninstall/i }));

    await waitFor(() => expect(api.uninstallPlugin).toHaveBeenCalledWith(UID, ID));
    expect(await screen.findByTestId("landed")).toHaveTextContent(TAB);
  });

  test("no Uninstall when the agent cannot uninstall; says why instead", async () => {
    renderPage({ ...DETAIL, can_uninstall: false });
    await screen.findByRole("heading", { name: "hud" });
    expect(screen.queryByRole("button", { name: /uninstall/i })).not.toBeInTheDocument();
    expect(screen.getByText(en.agents.pluginsTab.footnote.claudeNoCli)).toBeInTheDocument();
  });

  test("a plugin with no cache shows it is not on disk and contributes nothing", async () => {
    renderPage({
      ...DETAIL,
      plugin: { ...DETAIL.plugin, cache_present: false },
      install_path: null,
      skills: [],
      commands: [],
      agents: [],
      hooks: [],
      mcp_servers: [],
    });
    await screen.findByRole("heading", { name: "hud" });
    expect(screen.getByText(en.agents.pluginsTab.cacheMissing)).toBeInTheDocument();
    expect(screen.getByText(en.agents.pluginDetail.notOnDisk)).toBeInTheDocument();
    expect(screen.getByText(en.agents.pluginDetail.noContents)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en.fileActions.reveal })).not.toBeInTheDocument();
  });

  test("a failed read shows the error with a way back", async () => {
    renderPage(new Error("plugin not found: hud@claude-hud"));
    expect(await screen.findByText(en.agents.pluginDetail.loadFailed)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to plugins/i })).toHaveAttribute("href", TAB);
  });

  test("en and zh carry the same agents.pluginDetail keys", () => {
    const enKeys = Object.keys(en.agents.pluginDetail).sort();
    expect(enKeys.length).toBeGreaterThan(0);
    expect(Object.keys(zh.agents.pluginDetail).sort()).toEqual(enKeys);
  });
});
