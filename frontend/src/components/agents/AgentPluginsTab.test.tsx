// src/components/agents/AgentPluginsTab.test.tsx — the agent's Plugins tab, one table of every installed plugin.
//
// Every plugin is the agent's own; a row shows version, marketplace and state,
// an enabled switch and Uninstall (only when the listing says it can run), and
// its name opens the plugin's page — rows do not expand. Toggle and uninstall
// are addressed to the agent's uid, which is not its type, so the assertions
// spell the uid. Only the network boundary (`agentsApi`) is mocked.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentPluginsTab } from "./AgentPluginsTab";
import en from "@/i18n/locales/en.json";
import type { AgentOut, PluginOut, PluginsResponse } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: { plugins: vi.fn(), togglePlugin: vi.fn(), uninstallPlugin: vi.fn() },
}));
// No managed agent to ask: a hand-off offers Copy prompt only.
vi.mock("@/lib/hooks/useAgentProviders", () => ({ useAgentProviders: () => ({ data: [] }) }));
const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

function agent(type: AgentOut["type"]): AgentOut {
  return {
    uid: `u-${type}-agent`,
    name: type,
    type,
    config_dir: "/home/u/.claude",
    display_name: type === "codex" ? "Codex" : "Claude Code",
    model: null,
    effort: null,
    tier_models: null,
    wire_api: null,
    version: null,
    install_handoff: null,
    state: "installed_active",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function plugin(over: Partial<PluginOut> & Pick<PluginOut, "id" | "name">): PluginOut {
  return {
    author: null,
    commands: [],
    description: null,
    homepage: null,
    mcp_servers: [],
    skills: [],
    version: null,
    marketplace: "claude-plugins-official",
    enabled: true,
    cache_present: true,
    ...over,
  };
}

const SUPERPOWERS = plugin({
  id: "superpowers@superpowers-marketplace",
  name: "superpowers",
  marketplace: "superpowers-marketplace",
  version: "5.2.0",
  description: "Skills library: TDD, debugging, collaboration",
  skills: ["tdd", "debugging", "brainstorming", "plans"],
});
const REVIEW = plugin({ id: "code-review@official", name: "code-review", enabled: false });
const FRONTEND = plugin({
  id: "frontend-design@official",
  name: "frontend-design",
  cache_present: false,
});

function Landed() {
  const loc = useLocation();
  return <div data-testid="landed">{`${loc.pathname}${loc.search}`}</div>;
}

function renderTab(
  data: Partial<PluginsResponse>,
  type: AgentOut["type"] = "claude_code",
  over: Partial<AgentOut> = {},
) {
  api.plugins.mockResolvedValue({
    items: [],
    marketplaces: [],
    parse_errors: [],
    can_uninstall: true,
    ...data,
  });
  api.togglePlugin.mockResolvedValue(undefined);
  api.uninstallPlugin.mockResolvedValue(undefined);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/agents/${type}/plugins`]}>
        <Routes>
          <Route path="/agents/:type/plugins" element={children} />
          <Route path="/agents/:type/plugins/:pluginId" element={<Landed />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(<AgentPluginsTab agent={{ ...agent(type), ...over }} />, { wrapper: Wrapper });
}

const rowOf = async (text: string) => (await screen.findByText(text)).closest("tr") as HTMLElement;

afterEach(() => vi.clearAllMocks());

describe("AgentPluginsTab", () => {
  test("lists every plugin with version, marketplace and state", async () => {
    renderTab({ items: [SUPERPOWERS, REVIEW, FRONTEND] });
    expect(
      await screen.findByText("3 plugins · all the agent’s own · 2 enabled"),
    ).toBeInTheDocument();
    const sp = await rowOf("superpowers");
    expect(within(sp).getByText("5.2.0")).toBeInTheDocument();
    expect(within(sp).getByText("superpowers-marketplace")).toBeInTheDocument();
    expect(within(sp).getByText(SUPERPOWERS.description!)).toBeInTheDocument();
    expect(within(sp).getByText("Enabled")).toBeInTheDocument();
    expect(within(await rowOf("code-review")).getByText("Disabled")).toBeInTheDocument();
    expect(within(await rowOf("frontend-design")).getByText("Cache missing")).toBeInTheDocument();
    expect(screen.getByText(en.agents.pluginsTab.footnote.claude)).toBeInTheDocument();
  });

  acceptance("agent-registry", "toggle a plugin's enabled state", async () => {
    renderTab({ items: [SUPERPOWERS] });
    fireEvent.click(await screen.findByRole("switch", { name: "Enabled: superpowers" }));
    await waitFor(() =>
      expect(api.togglePlugin).toHaveBeenCalledWith("u-claude_code-agent", SUPERPOWERS.id, false),
    );
  });

  test("Uninstall confirms with Claude Code's own command, then uninstalls", async () => {
    renderTab({ items: [SUPERPOWERS] });
    fireEvent.click(await screen.findByRole("button", { name: "Uninstall superpowers" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Uninstall superpowers?")).toBeInTheDocument();
    expect(
      within(dialog).getByText(`claude plugin uninstall ${SUPERPOWERS.id}`),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Its 4 bundled skills go with it\./)).toBeInTheDocument();
    expect(api.uninstallPlugin).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Uninstall" }));
    await waitFor(() =>
      expect(api.uninstallPlugin).toHaveBeenCalledWith("u-claude_code-agent", SUPERPOWERS.id),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("Codex's uninstall says it drops the config.toml entry", async () => {
    renderTab({ items: [SUPERPOWERS] }, "codex");
    fireEvent.click(await screen.findByRole("button", { name: "Uninstall superpowers" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(`[plugins."${SUPERPOWERS.id}"]`)).toBeInTheDocument();
    expect(screen.getByText(en.agents.pluginsTab.footnote.codex)).toBeInTheDocument();
  });

  acceptance(
    "agent-registry",
    "hide the uninstall affordance when the uninstall cannot run",
    async () => {
      renderTab({ items: [SUPERPOWERS], can_uninstall: false });
      await screen.findByText("superpowers");
      expect(screen.queryByRole("button", { name: /uninstall/i })).not.toBeInTheDocument();
      expect(screen.getByText(en.agents.pluginsTab.footnote.claudeNoCli)).toBeInTheDocument();
    },
  );

  test("with Claude Code's program gone, the tab offers its reinstall prompt", async () => {
    renderTab({ items: [SUPERPOWERS], can_uninstall: false }, "claude_code", {
      state: "config_only",
      install_handoff: { prompt: "Please reinstall Claude Code on this machine." },
    });
    await screen.findByText("superpowers");
    expect(screen.getByText(/program isn’t found on this machine/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
  });

  acceptance("agent-registry", "open a plugin's detail page from the Plugins tab", async () => {
    // The Plugins-tab half of the scenario: rows do not expand, and the
    // plugin's name opens its page under this tab. The page half is in
    // AgentPluginPage.test.tsx.
    renderTab({ items: [SUPERPOWERS] });
    const link = await screen.findByRole("link", { name: "superpowers" });
    expect(document.querySelector("tr[aria-expanded]")).toBeNull();
    fireEvent.click(link);
    expect(await screen.findByTestId("landed")).toHaveTextContent(
      `/agents/claude_code/plugins/${encodeURIComponent(SUPERPOWERS.id)}`,
    );
  });

  // Scenario (revise-web-ui-ia, agent-registry): "the owner filter narrows an installed-kind tab"
  test("the Coffer filter shows nothing, since Coffer installs no plugins", async () => {
    renderTab({ items: [SUPERPOWERS, REVIEW] });
    await screen.findByText("superpowers");
    fireEvent.click(screen.getByRole("radio", { name: "Coffer’s" }));
    expect(screen.queryByText("superpowers")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "The agent’s own" }));
    expect(screen.getByText("superpowers")).toBeInTheDocument();
  });

  test("search narrows by name", async () => {
    renderTab({ items: [SUPERPOWERS, REVIEW] });
    await screen.findByText("superpowers");
    fireEvent.change(screen.getByLabelText("Search plugins"), { target: { value: "review" } });
    expect(screen.queryByText("superpowers")).not.toBeInTheDocument();
    expect(screen.getByText("code-review")).toBeInTheDocument();
  });

  test("a config that does not parse is an alert naming the file", async () => {
    renderTab({
      items: [SUPERPOWERS],
      parse_errors: [{ source: "config.toml", path: "/home/u/.codex/config.toml", error: "bad" }],
    });
    expect(
      await screen.findByText("Couldn’t read /home/u/.codex/config.toml: bad"),
    ).toBeInTheDocument();
  });

  test("an agent with no plugins shows the empty state naming it", async () => {
    renderTab({ items: [] }, "codex");
    expect(await screen.findByText("Codex has no plugins")).toBeInTheDocument();
    expect(screen.getByText("Plugins Codex installs show up here, read-only.")).toBeInTheDocument();
  });
});
