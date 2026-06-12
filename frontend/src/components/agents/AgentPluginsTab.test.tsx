// frontend/src/components/agents/AgentPluginsTab.test.tsx
//
// Tests for the agent Plugins tab:
//   - Grouped rendering by marketplace
//   - Toggle calls the API
//   - Cache-missing badge rendered
//   - codex agent shows Uninstall button + confirm dialog → api call
//   - claude_code agent hides Uninstall + shows hint text
//   - parse_errors surface as an Alert banner
//   - en/zh key parity for agents.workspace.pluginsTab
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentPluginsTab } from "./AgentPluginsTab";
import type { AgentOut, PluginsResponse } from "@/lib/api/agents";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    plugins: vi.fn(),
    togglePlugin: vi.fn(),
    uninstallPlugin: vi.fn(),
  },
}));

const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const CODEX_AGENT: AgentOut = {
  name: "codex-agent",
  type: "codex",
  config_dir: "/home/u/.codex",
  description: null,
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

const CLAUDE_AGENT: AgentOut = {
  name: "cc-agent",
  type: "claude_code",
  config_dir: "/home/u/.claude",
  description: null,
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

const PLUGIN_A = {
  id: "npm:@scope/plugin-a",
  name: "plugin-a",
  marketplace: "npm",
  enabled: true,
  cache_present: true,
};

const PLUGIN_B = {
  id: "gh:owner/plugin-b",
  name: "plugin-b",
  marketplace: "github",
  enabled: false,
  cache_present: false,
};

const MARKETPLACES = [
  { name: "npm", source_type: "npm", source: "https://registry.npmjs.org" },
  { name: "github", source_type: "github", source: "https://github.com" },
];

function stub(overrides: Partial<PluginsResponse> = {}) {
  api.plugins.mockResolvedValue({
    items: [PLUGIN_A, PLUGIN_B],
    marketplaces: MARKETPLACES,
    parse_errors: [],
    ...overrides,
  });
  api.togglePlugin.mockResolvedValue(undefined);
  api.uninstallPlugin.mockResolvedValue(undefined);
}

function renderTab(agent: AgentOut = CODEX_AGENT) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<AgentPluginsTab agent={agent} />, { wrapper: Wrapper });
}

afterEach(() => vi.clearAllMocks());

describe("AgentPluginsTab", () => {
  test("renders plugins grouped by marketplace with group headers", async () => {
    stub();
    renderTab();

    // Both plugin names appear.
    expect(await screen.findByText("plugin-a")).toBeInTheDocument();
    expect(screen.getByText("plugin-b")).toBeInTheDocument();

    // Marketplace group headers appear.
    expect(screen.getByText(/Marketplace: npm/)).toBeInTheDocument();
    expect(screen.getByText(/Marketplace: github/)).toBeInTheDocument();
  });

  test("marketplace source shown in group header when available", async () => {
    stub();
    renderTab();

    await screen.findByText("plugin-a");
    expect(screen.getByText(/registry\.npmjs\.org/)).toBeInTheDocument();
  });

  test("per-marketplace search filters rows by plugin name", async () => {
    // Two plugins in the same marketplace so the search has something to hide.
    const PLUGIN_C = {
      id: "npm:@scope/plugin-c",
      name: "plugin-c",
      marketplace: "npm",
      enabled: true,
      cache_present: true,
    };
    stub({ items: [PLUGIN_A, PLUGIN_C], marketplaces: [MARKETPLACES[0]] });
    renderTab();

    expect(await screen.findByText("plugin-a")).toBeInTheDocument();
    expect(screen.getByText("plugin-c")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search plugins"), {
      target: { value: "plugin-c" },
    });

    expect(screen.getByText("plugin-c")).toBeInTheDocument();
    expect(screen.queryByText("plugin-a")).not.toBeInTheDocument();
  });

  test("toggle Switch calls the API with the plugin id and new enabled flag", async () => {
    stub();
    renderTab();

    const switches = await screen.findAllByRole("switch");
    // plugin-a is enabled (true) → toggling should flip to false.
    fireEvent.click(switches[0]);
    await waitFor(() =>
      expect(api.togglePlugin).toHaveBeenCalledWith(
        CODEX_AGENT.name,
        PLUGIN_A.id,
        false,
      ),
    );
  });

  test("cache-missing badge rendered for plugin with cache_present=false", async () => {
    stub();
    renderTab();

    await screen.findByText("plugin-b");
    expect(screen.getByText(/cache missing/i)).toBeInTheDocument();
  });

  test("no cache badge for plugin with cache_present=true", async () => {
    stub({ items: [PLUGIN_A] });
    renderTab();

    await screen.findByText("plugin-a");
    expect(screen.queryByText(/cache missing/i)).not.toBeInTheDocument();
  });

  test("codex agent: Uninstall button shown; confirm dialog calls the API", async () => {
    stub();
    renderTab(CODEX_AGENT);

    await screen.findByText("plugin-a");
    const buttons = screen.getAllByRole("button", { name: /uninstall/i });
    expect(buttons.length).toBeGreaterThan(0);

    // Click the first Uninstall button.
    fireEvent.click(buttons[0]);
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/config entry and the cache directory/i),
    ).toBeInTheDocument();

    expect(api.uninstallPlugin).not.toHaveBeenCalled();
    // Confirm uninstall.
    fireEvent.click(within(dialog).getByRole("button", { name: /uninstall/i }));
    await waitFor(() =>
      expect(api.uninstallPlugin).toHaveBeenCalledWith(CODEX_AGENT.name, PLUGIN_A.id),
    );
  });

  test("claude_code agent: no Uninstall button; hint text shown instead", async () => {
    stub();
    renderTab(CLAUDE_AGENT);

    await screen.findByText("plugin-a");
    expect(screen.queryByRole("button", { name: /uninstall/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/claude plugin/i).length).toBeGreaterThan(0);
  });

  test("parse_errors renders the degraded-config banner", async () => {
    stub({
      parse_errors: [
        { source: "plugins.toml", path: "/home/u/.codex/plugins.toml", error: "invalid toml" },
      ],
    });
    renderTab();
    expect(
      await screen.findByText(/failed to parse config — this file is read-only/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/plugins\.toml: invalid toml/)).toBeInTheDocument();
  });

  test("empty state shows the no-plugins message", async () => {
    stub({ items: [], marketplaces: [] });
    renderTab();
    expect(await screen.findByText(/no plugins installed/i)).toBeInTheDocument();
  });

  test("en and zh locales carry the same agents.workspace.pluginsTab keys", () => {
    const enKeys = Object.keys(en.agents.workspace.pluginsTab).sort();
    const zhKeys = Object.keys(zh.agents.workspace.pluginsTab).sort();
    expect(enKeys.length).toBeGreaterThan(0);
    expect(zhKeys).toEqual(enKeys);
  });

  test("en and zh locales both define agents.workspace.plugins as a string", () => {
    expect(typeof en.agents.workspace.plugins).toBe("string");
    expect(typeof zh.agents.workspace.plugins).toBe("string");
  });
});
