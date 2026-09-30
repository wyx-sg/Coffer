// src/components/agents/AgentMcpServersTab.test.tsx — the agent's MCP servers tab: gateway servers and direct entries in one table.
//
// Covered: Coffer's servers that reach the agent (Connected by the agent's
// Coffer connection) beside its direct entries (Bypasses Coffer / Duplicate),
// the `coffer` entry never being a row, a name opening the entry's page,
// Adopt through the dialog, Remove duplicate behind a confirm, a config file
// that failed to parse, and the shared empty state. Hooks run for real against
// the mocked wire (agentsApi + the resources client).
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentMcpServersTab } from "./AgentMcpServersTab";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentOut, McpEntryOut } from "@/lib/api/agents";
import { getApiClient } from "@/lib/api/client";
import { acceptance } from "@/test/acceptance";
import { mockApiClient } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    mcpEntries: vi.fn(),
    connection: vi.fn(),
    listConfigFiles: vi.fn(),
    removeMcpEntry: vi.fn(),
    adoptMcpEntry: vi.fn(),
  },
}));
const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const AGENT: AgentOut = {
  uid: "u-cc",
  name: "claude_code",
  type: "claude_code",
  config_dir: "/Users/me/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  wire_api: null,
  version: null,
  install_handoff: null,
  state: "installed_active",
  created_at: "",
  updated_at: "",
};

function entry(name: string, extra: Partial<McpEntryOut> = {}): McpEntryOut {
  return {
    name,
    source: "global",
    transport: "stdio",
    command: "npx",
    args: ["-y", `@acme/${name}`],
    env_keys: [],
    secret_keys: [],
    url: null,
    header_keys: [],
    enabled: null,
    is_coffer: false,
    matches_resource: null,
    ...extra,
  };
}

const GATEWAY = entry("coffer", { is_coffer: true, command: "coffer-mcp-shim", args: [] });
const POSTGRES = entry("postgres-local", {
  command: "uvx",
  args: ["mcp-server-postgres"],
  env_keys: ["DATABASE_URL", "PGSSLMODE"],
  secret_keys: ["DATABASE_URL"],
});
const GITHUB_COPY = entry("github", { matches_resource: "github" });

const SERVERS = [
  { uid: "r-gh", kind: "mcp_server", name: "github", enabled: true, scope: null },
  {
    uid: "r-fs",
    kind: "mcp_server",
    name: "filesystem",
    enabled: true,
    scope: { agents: ["u-cc"] },
  },
  { uid: "r-off", kind: "mcp_server", name: "disabled-one", enabled: false, scope: null },
  {
    uid: "r-cx",
    kind: "mcp_server",
    name: "codex-only",
    enabled: true,
    scope: { agents: ["u-cx"] },
  },
];

function stub({
  items = [GATEWAY, POSTGRES, GITHUB_COPY],
  parse_errors = [] as { source: string; path: string; error: string }[],
  mcpInstalled = true,
  servers = SERVERS,
} = {}) {
  vi.mocked(getApiClient).mockReturnValue(
    mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: { resources: servers }, error: undefined }),
    }) as unknown as ReturnType<typeof getApiClient>,
  );
  api.mcpEntries.mockResolvedValue({ items, parse_errors });
  api.connection.mockResolvedValue({
    state: mcpInstalled ? "connected" : "disconnected",
    parts: [{ key: "mcp", installed: mcpInstalled, detail: null }],
  } as Awaited<ReturnType<typeof agentsApi.connection>>);
  api.listConfigFiles.mockResolvedValue({
    items: [{ key: "global", path: "/Users/me/.claude.json" }],
  } as Awaited<ReturnType<typeof agentsApi.listConfigFiles>>);
  api.removeMcpEntry.mockResolvedValue(undefined);
  api.adoptMcpEntry.mockResolvedValue({ uid: "r-pg", kind: "mcp_server", name: "postgres-local" });
}

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{`${loc.pathname}${loc.search}`}</p>;
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/agents/claude_code/mcp-servers"]}>
          <Routes>
            <Route
              path="/agents/:type/mcp-servers"
              element={<AgentMcpServersTab agent={AGENT} />}
            />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const rowOf = (name: string) =>
  screen.getAllByText(name, { selector: "a, span" }).map((el) => el.closest("tr") as HTMLElement);

afterEach(() => vi.clearAllMocks());

describe("AgentMcpServersTab", () => {
  test("lists the gateway servers that reach the agent beside its direct entries", async () => {
    stub();
    renderTab();

    expect(
      await screen.findByText(
        "4 servers · 2 through the Coffer gateway · 2 directly in ~/.claude.json",
      ),
    ).toBeInTheDocument();
    // The `coffer` entry is the gateway itself, not a row; out-of-reach servers are absent.
    expect(screen.queryByText("coffer-mcp-shim")).not.toBeInTheDocument();
    expect(screen.queryByText("disabled-one")).not.toBeInTheDocument();
    expect(screen.queryByText("codex-only")).not.toBeInTheDocument();

    const [pg] = rowOf("postgres-local");
    expect(within(pg).getByText("1 secret in env")).toBeInTheDocument();
    expect(within(pg).getByText("uvx mcp-server-postgres")).toBeInTheDocument();
    expect(within(pg).getByText("~/.claude.json")).toBeInTheDocument();
    expect(within(pg).getByText("Bypasses Coffer")).toBeInTheDocument();
    expect(within(pg).getByText("The agent’s own")).toBeInTheDocument();

    const [fs] = rowOf("filesystem");
    expect(within(fs).getByText("coffer gateway")).toBeInTheDocument();
    expect(within(fs).getByText("coffer entry")).toBeInTheDocument();
    expect(await within(fs).findByText("Connected")).toBeInTheDocument();
    expect(within(fs).getByText("Coffer’s")).toBeInTheDocument();
  });

  test("Coffer's servers read Not connected until the agent has the gateway entry", async () => {
    stub({ mcpInstalled: false });
    renderTab();
    const [fs] = await waitFor(() => rowOf("filesystem"));
    expect(await within(fs).findByText("Not connected")).toBeInTheDocument();
  });

  test("a direct entry's name opens its page, and Manage opens a Coffer server's", async () => {
    stub();
    renderTab();
    expect(await screen.findByRole("link", { name: "postgres-local" })).toHaveAttribute(
      "href",
      "/agents/claude_code/mcp-servers/postgres-local?source=global",
    );
    fireEvent.click(screen.getByRole("button", { name: "Manage: filesystem" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/mcp-servers/filesystem");
  });

  test("Adopt opens the dialog and adopts the entry with its secret references", async () => {
    stub();
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "Adopt: postgres-local" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Adopt postgres-local")).toBeInTheDocument();
    expect(within(dialog).getByText("PGSSLMODE")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt" }));
    await waitFor(() =>
      expect(api.adoptMcpEntry).toHaveBeenCalledWith("u-cc", "postgres-local", {
        source: "global",
        secrets: { DATABASE_URL: "mcp/claude_code/postgres-local/DATABASE_URL" },
      }),
    );
  });

  acceptance("agent-registry", "a duplicate direct MCP entry can be removed", async () => {
    stub();
    renderTab();
    await screen.findByText("Duplicate of github in Coffer");
    expect(rowOf("github")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Remove duplicate: github" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Remove github from ~/.claude.json?")).toBeInTheDocument();
    api.mcpEntries.mockResolvedValue({ items: [GATEWAY, POSTGRES], parse_errors: [] });
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() =>
      expect(api.removeMcpEntry).toHaveBeenCalledWith("u-cc", "github", "global"),
    );
    await waitFor(() => expect(rowOf("github")).toHaveLength(1));
    expect(within(rowOf("github")[0]).getByText("Coffer’s")).toBeInTheDocument();
  });

  test("a config file that failed to parse is named, and its entries stay read-only", async () => {
    stub({
      parse_errors: [
        { source: "global", path: "/Users/me/.claude.json", error: "Line 214, column 3" },
      ],
    });
    renderTab();
    expect(
      await screen.findByText("Couldn’t parse ~/.claude.json — shown read-only"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Read-only")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Adopt: postgres-local" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove duplicate: github" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Open in Config files" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/agents/claude_code/config");
  });

  test("an agent with no MCP servers shows the shared empty state", async () => {
    stub({ items: [GATEWAY], servers: [] });
    renderTab();
    expect(await screen.findByText("Claude Code has no MCP servers")).toBeInTheDocument();
  });
});
