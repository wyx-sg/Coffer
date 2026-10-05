// src/components/agents/AgentPluginsTab.test.tsx — the agent's Plugins tab, one list of every installed plugin.
//
// Every plugin is the agent's own; a row shows description · version ·
// marketplace, a state word only for a problem, an enabled switch and a ⋯ menu
// holding Uninstall… (disabled with the reason while it cannot run), and its
// name opens the info dialog — rows do not expand. Toggle and uninstall
// are addressed to the agent's uid, which is not its type, so the assertions
// spell the uid. Only the network boundary (`agentsApi`) is mocked.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentPluginsTab } from "./AgentPluginsTab";
import type { AgentOut } from "@/lib/api/agents";
import type { PluginOut, PluginsResponse } from "@/lib/api/agents-workspace";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    plugins: vi.fn(),
    plugin: vi.fn(),
    togglePlugin: vi.fn(),
    uninstallPlugin: vi.fn(),
  },
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
    tier_models: null,
    version: null,
    install_handoff: null,
    connection_uid: null,
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
  test("lists every plugin with description, version and marketplace; only a problem gets a state word", async () => {
    renderTab({ items: [SUPERPOWERS, REVIEW, FRONTEND] });
    const sp = await rowOf("superpowers");
    expect(within(sp).getByText("5.2.0")).toBeInTheDocument();
    expect(within(sp).getByText("superpowers-marketplace")).toBeInTheDocument();
    expect(within(sp).getByText(SUPERPOWERS.description!)).toBeInTheDocument();
    expect(within(sp).queryByText("Enabled")).toBeNull();
    expect(within(await rowOf("code-review")).queryByText("Off")).toBeNull();
    expect(within(await rowOf("frontend-design")).getByText("Cache missing")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
  });

  acceptance("agent-registry", "toggle a plugin's enabled state", async () => {
    renderTab({ items: [SUPERPOWERS] });
    fireEvent.click(await screen.findByRole("switch", { name: "Enabled: superpowers" }));
    await waitFor(() =>
      expect(api.togglePlugin).toHaveBeenCalledWith("u-claude_code-agent", SUPERPOWERS.id, false),
    );
  });

  test("⋯ › Uninstall… confirms with Claude Code's own command, then uninstalls", async () => {
    renderTab({ items: [SUPERPOWERS] });
    fireEvent.click(await screen.findByRole("button", { name: "More for superpowers" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Uninstall…"]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Uninstall…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Uninstall superpowers?")).toBeInTheDocument();
    expect(dialog).toHaveTextContent(
      "Claude Code runs its own plugin uninstall command. The plugin’s entry and its cache are removed. Its 4 skills go with it.",
    );
    expect(api.uninstallPlugin).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Uninstall" }));
    await waitFor(() =>
      expect(api.uninstallPlugin).toHaveBeenCalledWith("u-claude_code-agent", SUPERPOWERS.id),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("Codex's uninstall says it drops the config.toml entry", async () => {
    renderTab({ items: [SUPERPOWERS] }, "codex");
    fireEvent.click(await screen.findByRole("button", { name: "More for superpowers" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Uninstall…" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(
      "Coffer removes the plugin’s entry from config.toml (a backup copy is kept in Coffer’s folder) and deletes its cache.",
    );
  });

  acceptance(
    "agent-registry",
    "hide the uninstall affordance when the uninstall cannot run",
    async () => {
      // The listing reports can_uninstall=false; the menu item is shown disabled, with the reason.
      renderTab({ items: [SUPERPOWERS], can_uninstall: false });
      fireEvent.click(await screen.findByRole("button", { name: "More for superpowers" }));
      const item = await screen.findByRole("menuitem", { name: /Uninstall…/ });
      expect(item).toBeDisabled();
      expect(item).toHaveTextContent("Claude Code isn’t on this Mac");
    },
  );

  test("with Claude Code's program gone, the list says so and offers the hand-off", async () => {
    renderTab({ items: [SUPERPOWERS], can_uninstall: false }, "claude_code", {
      state: "config_only",
      install_handoff: { prompt: "Please reinstall Claude Code on this machine." },
    });
    expect(
      await screen.findByText(
        "Claude Code isn’t on this Mac, so its plugins can’t be uninstalled here.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More info" })).toBeInTheDocument();
  });

  test("Codex has no program notice even when it cannot uninstall", async () => {
    renderTab({ items: [SUPERPOWERS], can_uninstall: false }, "codex");
    await screen.findByText("superpowers");
    expect(screen.queryByText(/isn’t on this Mac, so/)).toBeNull();
  });

  acceptance("agent-registry", "open a plugin's detail page from the Plugins tab", async () => {
    // Rows do not expand; the plugin's name opens a dialog saying what it is and
    // which skills, commands and MCP servers it provides, each section with its count.
    api.plugin.mockResolvedValue({
      plugin: SUPERPOWERS,
      install_path: "/Users/me/.claude/plugins/cache/m/superpowers/1.0.0",
      marketplace_source: null,
      can_uninstall: true,
      skills: [
        { name: "brainstorming", description: "Turns a rough idea into a design" },
        { name: "plans", description: null },
      ],
      commands: [],
      agents: [],
      hooks: ["SessionStart"],
      mcp_servers: ["docs"],
    } as never);
    renderTab({ items: [SUPERPOWERS] });
    const name = await screen.findByRole("button", { name: "superpowers" });
    expect(document.querySelector("tr[aria-expanded]")).toBeNull();
    fireEvent.click(name);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.className).toContain("max-w-[640px]");
    expect(await within(dialog).findByText("brainstorming")).toBeInTheDocument();
    expect(within(dialog).getByText("Turns a rough idea into a design")).toBeInTheDocument();
    expect(within(dialog).getByText("Skills")).toBeInTheDocument();
    expect(within(dialog).getByText("2")).toBeInTheDocument();
    expect(within(dialog).getByText("SessionStart")).toBeInTheDocument();
    expect(within(dialog).getByText("docs")).toBeInTheDocument();
    expect(
      within(dialog).getByText("~/.claude/plugins/cache/m/superpowers/1.0.0"),
    ).toBeInTheDocument();
    expect(within(dialog).getAllByRole("button", { name: "Close" })).toHaveLength(2);
  });

  test("search narrows by name", async () => {
    renderTab({ items: [SUPERPOWERS, REVIEW] });
    await screen.findByText("superpowers");
    fireEvent.change(screen.getByLabelText("Search plugins"), { target: { value: "review" } });
    expect(screen.queryByText("superpowers")).not.toBeInTheDocument();
    expect(screen.getByText("code-review")).toBeInTheDocument();
  });

  test("a config that does not parse is a warning naming the file", async () => {
    renderTab({
      items: [SUPERPOWERS],
      parse_errors: [{ source: "config.toml", path: "/home/u/.codex/config.toml", error: "bad" }],
    });
    expect(
      await screen.findByText("Couldn’t read /home/u/.codex/config.toml: bad"),
    ).toBeInTheDocument();
  });

  test("an agent with no plugins shows the shared empty box, search kept", async () => {
    renderTab({ items: [] }, "codex");
    expect(await screen.findByText("Codex has no plugins")).toBeInTheDocument();
    expect(screen.getByText("Plugins you install in Codex show up here.")).toBeInTheDocument();
    expect(screen.getByLabelText("Search plugins")).toBeInTheDocument();
  });
});
