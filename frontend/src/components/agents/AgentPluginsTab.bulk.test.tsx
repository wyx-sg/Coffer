// src/components/agents/AgentPluginsTab.bulk.test.tsx — acting on several plugins at once.
//
// Covered: Disable switching off only the plugins that are on and saying how
// many were already off, with no confirmation; a failed switch listed under the
// bar with Retry for just it; Uninstall… asking once, one request per plugin,
// and being disabled with the reason while the program is missing.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentPluginsTab } from "./AgentPluginsTab";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import type { PluginOut, PluginsResponse } from "@/lib/api/agents-workspace";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    plugins: vi.fn(),
    plugin: vi.fn(),
    togglePlugin: vi.fn(),
    uninstallPlugin: vi.fn(),
  },
}));
vi.mock("@/lib/hooks/useAgentProviders", () => ({ useAgentProviders: () => ({ data: [] }) }));
const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const AGENT: AgentOut = {
  uid: "u-cc",
  name: "claude_code",
  type: "claude_code",
  config_dir: "/home/u/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  version: null,
  install_handoff: null,
  connection_uid: null,
  state: "installed_active",
  created_at: "",
  updated_at: "",
};

function plugin(over: Partial<PluginOut> & Pick<PluginOut, "id" | "name">): PluginOut {
  return {
    author: null,
    commands: [],
    description: null,
    homepage: null,
    mcp_servers: [],
    skills: [],
    version: null,
    marketplace: "official",
    enabled: true,
    cache_present: true,
    ...over,
  };
}

const ONE = plugin({ id: "one@official", name: "one" });
const TWO = plugin({ id: "two@official", name: "two", skills: ["a", "b"] });
const OFF = plugin({ id: "off@official", name: "off", enabled: false });

function renderTab(data: Partial<PluginsResponse> = {}) {
  api.plugins.mockResolvedValue({
    items: [ONE, TWO, OFF],
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
      <ToastProvider>
        <MemoryRouter>{children}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
  return render(<AgentPluginsTab agent={AGENT} />, { wrapper: Wrapper });
}

const tick = (name: string) =>
  fireEvent.click(screen.getByRole("checkbox", { name: `Select ${name}` }));
const bar = () => screen.getByRole("region", { name: "Selected plugins" });

afterEach(() => vi.clearAllMocks());

describe("AgentPluginsTab — bulk", () => {
  acceptance("agent-registry", "enable, disable or uninstall several plugins at once", async () => {
    renderTab();
    await screen.findByText("one");
    tick("one");
    tick("two");
    tick("off");
    expect(within(bar()).getByText("3 of 3 selected")).toBeInTheDocument();
    fireEvent.click(within(bar()).getByRole("button", { name: "Disable" }));
    // No confirmation; only the two that are on are switched, one after another.
    await waitFor(() => expect(api.togglePlugin).toHaveBeenCalledTimes(2));
    expect(api.togglePlugin.mock.calls).toEqual([
      ["u-cc", "one@official", false],
      ["u-cc", "two@official", false],
    ]);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
      await screen.findByText(/Disabled 2 plugins\. 1 selected plugin is already off\./),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Selected plugins" })).toBeNull(),
    );

    // Uninstall… asks once, then sends one request per plugin.
    tick("one");
    tick("two");
    fireEvent.click(within(bar()).getByRole("button", { name: "Uninstall…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Uninstall 2 plugins?")).toBeInTheDocument();
    expect(within(dialog).getByText(/Its 2 skills go with it\./)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Uninstall 2 plugins" }));
    await waitFor(() => expect(api.uninstallPlugin).toHaveBeenCalledTimes(2));
    expect(api.uninstallPlugin.mock.calls).toEqual([
      ["u-cc", "one@official"],
      ["u-cc", "two@official"],
    ]);
  });

  test("Uninstall… is disabled with the reason while the program is missing", async () => {
    renderTab({ can_uninstall: false });
    await screen.findByText("one");
    tick("one");
    const uninstall = within(bar()).getByRole("button", { name: "Uninstall…" });
    expect(uninstall).toBeDisabled();
    expect(uninstall).toHaveAttribute("title", "Claude Code isn’t on this Mac");
  });

  test("a failed switch is listed under the bar and Retry sends only it", async () => {
    renderTab();
    api.togglePlugin.mockRejectedValueOnce(new ApiError("INTERNAL_ERROR", "disk full"));
    await screen.findByText("one");
    tick("one");
    tick("off");
    fireEvent.click(within(bar()).getByRole("button", { name: "Enable" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Enabled 0 of 1")).toBeInTheDocument();
    expect(within(alert).getByText("off")).toBeInTheDocument();
    // The selection stays so the person can see what was tried.
    expect(screen.getByRole("region", { name: "Selected plugins" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry 1 that failed" }));
    await waitFor(() => expect(api.togglePlugin).toHaveBeenCalledTimes(2));
    expect(api.togglePlugin.mock.calls[1]).toEqual(["u-cc", "off@official", true]);
  });
});
