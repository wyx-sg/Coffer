// src/pages/AgentMcpEntryPage.test.tsx — one direct MCP server of an agent, at /agents/:type/mcp-servers/:entry.
//
// What the agent's own config file holds for the entry, read-only, with secret
// values never shown; the header naming it a direct server of the agent; the
// way back to the agent's MCP servers tab; and the two writes — adopt (then on
// to the new managed server) and remove (then back to the tab).
//
// The API module is mocked at its boundary (`agentsApi`), and the fs actions
// too (their own suite covers the transport). The page is addressed by the
// agent's TYPE and the REST reads by its uid (`u-cc`), found through the
// per-type listing.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentMcpEntryPage } from "./AgentMcpEntryPage";
import { AgentMcpServersTab } from "@/components/agents/AgentMcpServersTab";
import type { AgentOut, McpEntryDetailOut } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";

// The MCP servers tab also lists Coffer's registered servers; none here.
vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({
    GET: vi.fn(() => Promise.resolve({ data: { resources: [] }, error: undefined })),
  }),
}));
vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    types: vi.fn(),
    get: vi.fn(),
    listConfigFiles: vi.fn(),
    connection: vi.fn(),
    mcpEntries: vi.fn(),
    mcpEntry: vi.fn(),
    removeMcpEntry: vi.fn(),
    adoptMcpEntry: vi.fn(),
  },
}));
const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const openMock = vi.fn(() => Promise.resolve());
const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: revealMock }),
}));

const AGENT: AgentOut = {
  uid: "u-cc",
  name: "cc",
  type: "claude_code",
  config_dir: "/home/u/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  wire_api: null,
  version: null,
  install_handoff: null,
  state: "installed_active",
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

const CONFIG_PATH = "/home/u/.claude.json";

const ENTRY: McpEntryDetailOut = {
  name: "skynet",
  source: "global",
  transport: "stdio",
  command: "skynet-mcp",
  args: ["--mcp=skynet-base", "--verbose"],
  env_keys: ["API_TOKEN", "LANG"],
  secret_keys: ["API_TOKEN"],
  url: null,
  header_keys: [],
  enabled: null,
  is_coffer: false,
  matches_resource: null,
  path: CONFIG_PATH,
  cwd: "/srv/skynet",
  extra: [
    { key: "bearer_token", value: null, masked: true },
    { key: "timeout", value: "30", masked: false },
  ],
};

/** Where the page navigated to, rendered so a test can read it. */
function Landed() {
  const loc = useLocation();
  return <div data-testid="landed">{`${loc.pathname}${loc.search}`}</div>;
}

const TYPE_ROW = {
  type: "claude_code",
  uid: "u-cc",
  name: "claude_code",
  display_name: "Claude Code",
  state: "installed_active",
  addable: true,
  config_dir: "/home/u/.claude",
  standard_config_dir: "/home/u/.claude",
  other_config_dir: null,
  default_skill_dir: "/home/u/.claude/skills",
  version: null,
  install_handoff: null,
} as const;

function stub(entry: Partial<McpEntryDetailOut> = {}) {
  api.types.mockResolvedValue({ types: [TYPE_ROW], install_handoff: null });
  api.get.mockResolvedValue(AGENT);
  api.listConfigFiles.mockResolvedValue({ items: [] });
  api.mcpEntry.mockResolvedValue({ ...ENTRY, ...entry });
  api.removeMcpEntry.mockResolvedValue(undefined);
}

function renderAt(url = `/agents/claude_code/mcp-servers/skynet?source=global`) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter
        initialEntries={[{ pathname: url.split("?")[0], search: `?${url.split("?")[1] ?? ""}` }]}
      >
        <Routes>
          <Route path="/agents/:type/mcp-servers/:entry" element={<AgentMcpEntryPage />} />
          <Route path="/agents/:type/mcp-servers" element={<Landed />} />
          <Route path="/mcp-servers/:name/:tab?" element={<Landed />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentMcpEntryPage", () => {
  acceptance(
    "agent-registry",
    "open a direct MCP server's detail page from the agent",
    async () => {
      // Start on the agent's MCP servers tab and click the server's name.
      stub();
      api.connection.mockResolvedValue({
        state: "connected",
        parts: [{ key: "mcp", installed: true, detail: "/opt/coffer-mcp-shim" }],
      });
      api.mcpEntries.mockResolvedValue({ items: [ENTRY], parse_errors: [] });
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={["/agents/claude_code/mcp-servers"]}>
            <Routes>
              <Route
                path="/agents/:type/mcp-servers"
                element={<AgentMcpServersTab agent={AGENT} />}
              />
              <Route path="/agents/:type/mcp-servers/:entry" element={<AgentMcpEntryPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      fireEvent.click(await screen.findByRole("link", { name: "skynet" }));

      // The detail page reads that one entry, addressed by uid + name + file.
      await screen.findByText(CONFIG_PATH);
      expect(api.mcpEntry).toHaveBeenCalledWith("u-cc", "skynet", "global");
      expect(screen.getByText("Direct server of Claude Code")).toBeInTheDocument();
      expect(screen.getByText("skynet-mcp")).toBeInTheDocument();
      expect(screen.getByText("--mcp=skynet-base")).toBeInTheDocument();
      expect(screen.getByText("/srv/skynet")).toBeInTheDocument();
      expect(screen.getByText(CONFIG_PATH)).toBeInTheDocument();
      // Env names only, marked set / secret; a masked extra key says hidden.
      expect(screen.getByText("API_TOKEN")).toBeInTheDocument();
      expect(screen.getByText("secret · hidden")).toBeInTheDocument();
      expect(screen.getByText("set")).toBeInTheDocument();
      expect(screen.getByText("bearer_token")).toBeInTheDocument();
      expect(screen.getByText("hidden")).toBeInTheDocument();
      expect(screen.getByText("30")).toBeInTheDocument();
      // The way back is the agent's MCP servers tab, addressed by its type.
      expect(screen.getByRole("link", { name: /Back to MCP servers/ })).toHaveAttribute(
        "href",
        "/agents/claude_code/mcp-servers",
      );
    },
  );

  test("an old uid address is replaced by the type address", async () => {
    stub();
    renderAt("/agents/u-cc/mcp-servers/skynet?source=global");
    await screen.findByText(CONFIG_PATH);
    expect(screen.getByRole("link", { name: /Back to MCP servers/ })).toHaveAttribute(
      "href",
      "/agents/claude_code/mcp-servers",
    );
  });

  test("an http entry shows its URL and header names; values never render", async () => {
    stub({
      transport: "http",
      command: null,
      args: [],
      url: "https://gas.example/mcp",
      env_keys: [],
      header_keys: ["Authorization"],
      secret_keys: ["Authorization"],
      cwd: null,
      extra: [],
    });
    renderAt();
    await screen.findByText("https://gas.example/mcp");
    expect(screen.getByText("HTTP headers")).toBeInTheDocument();
    expect(screen.getByText("Authorization")).toBeInTheDocument();
    expect(screen.getByText("secret · hidden")).toBeInTheDocument();
    expect(screen.queryByText("Command")).not.toBeInTheDocument();
    expect(screen.queryByText("Working directory")).not.toBeInTheDocument();
  });

  test("the config file can be opened in the editor and revealed", async () => {
    stub();
    renderAt();
    await screen.findByText(CONFIG_PATH);
    fireEvent.click(screen.getByRole("button", { name: /Open in editor/ }));
    fireEvent.click(screen.getByRole("button", { name: /Reveal/ }));
    await waitFor(() => expect(openMock).toHaveBeenCalledWith(CONFIG_PATH, expect.anything()));
    expect(revealMock).toHaveBeenCalledWith(CONFIG_PATH);
  });

  test("an equivalent managed server is named under the title", async () => {
    stub({ matches_resource: "skynet-managed" });
    renderAt();
    expect(await screen.findByText("Duplicate of skynet-managed in Coffer")).toBeInTheDocument();
  });

  test("adopting moves on to the new managed server's page", async () => {
    stub({ secret_keys: [], env_keys: [] });
    api.adoptMcpEntry.mockResolvedValue({ uid: "srv-uid-1", kind: "mcp_server", name: "skynet" });
    renderAt();
    await screen.findByText(CONFIG_PATH);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Adopt" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt" }));
    await waitFor(() =>
      // Addressed by the server's fixed name, not its uid (revise-web-ui-ia).
      expect(screen.getByTestId("landed")).toHaveTextContent(/^\/mcp-servers\/skynet$/),
    );
    expect(api.adoptMcpEntry).toHaveBeenCalledWith("u-cc", "skynet", { source: "global" });
  });

  test("removing (after the confirm) returns to the agent's MCP servers tab", async () => {
    stub();
    renderAt();
    await screen.findByText(CONFIG_PATH);
    fireEvent.click(screen.getByRole("button", { name: /Remove/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Remove skynet from ~/.claude.json?")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(screen.getByTestId("landed")).toHaveTextContent("/agents/claude_code/mcp-servers"),
    );
    expect(api.removeMcpEntry).toHaveBeenCalledWith("u-cc", "skynet", "global");
  });

  test("a failed read says why, and still offers the way back", async () => {
    stub();
    api.mcpEntry.mockRejectedValue(new Error("MCP entry not found"));
    renderAt();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to/ })).toHaveAttribute(
      "href",
      "/agents/claude_code/mcp-servers",
    );
  });
});
