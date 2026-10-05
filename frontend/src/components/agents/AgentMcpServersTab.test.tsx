// src/components/agents/AgentMcpServersTab.test.tsx — the agent's MCP servers tab: "From Coffer" in one row, then the agent's own entries.
//
// Covered: Coffer's servers that reach the agent as one row (count, first five
// names, a link to the MCP servers page filtered to this agent) and never as
// rows, the `coffer` entry never being one, the agent's own entries with their
// state, one button and a ⋯ menu holding Remove… only, the entry dialog (JSON,
// Close, Remove, Adopt), Adopt through the dialog, Remove duplicate behind a
// confirm, a config file that failed to parse (inline warning, read-only rows,
// a way to the Config files tab), and the shared empty box. Hooks run for real
// against the mocked wire (agentsApi + the resources client).
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AgentMcpServersTab } from "./AgentMcpServersTab";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import type { McpEntryOut } from "@/lib/api/agents-workspace";
import { getApiClient } from "@/lib/api/client";
import { fsApi } from "@/lib/api/fs";
import { acceptance } from "@/test/acceptance";
import { mockApiClient } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));
vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    mcpEntries: vi.fn(),
    mcpEntry: vi.fn(),
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
  tier_models: null,
  version: null,
  install_handoff: null,
  connection_uid: null,
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
const LINEAR = entry("linear");
const GITHUB_COPY = entry("github", { matches_resource: "github" });

const TOOL_GROUP = {
  uid: "r-billing",
  kind: "mcp_server",
  name: "billing",
  enabled: true,
  scope: null,
  config: { transport: { type: "http_api" } },
};

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
  items = [GATEWAY, POSTGRES, LINEAR, GITHUB_COPY],
  parse_errors = [] as { source: string; path: string; error: string }[],
  servers = SERVERS,
} = {}) {
  vi.mocked(getApiClient).mockReturnValue(
    mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: { resources: servers }, error: undefined }),
    }) as unknown as ReturnType<typeof getApiClient>,
  );
  api.mcpEntries.mockResolvedValue({ items, parse_errors });
  api.listConfigFiles.mockResolvedValue({
    items: [{ key: "global", path: "/Users/me/.claude.json" }],
  } as Awaited<ReturnType<typeof agentsApi.listConfigFiles>>);
  api.removeMcpEntry.mockResolvedValue(undefined);
  api.adoptMcpEntry.mockResolvedValue({ uid: "r-pg", kind: "mcp_server", name: "postgres-local" });
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
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const rowOf = (name: string) => screen.getByRole("button", { name }).closest("li") as HTMLElement;

afterEach(() => vi.clearAllMocks());

describe("AgentMcpServersTab", () => {
  test("Coffer's servers are one row — count, names, a link filtered to this agent — and never rows", async () => {
    stub();
    renderTab();
    expect(await screen.findByText("2 servers through Coffer")).toBeInTheDocument();
    expect(screen.getByText("github · filesystem")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open MCP servers/ })).toHaveAttribute(
      "href",
      "/mcp-servers?agent=u-cc",
    );
    // The `coffer` entry is the gateway itself; out-of-reach servers are absent.
    expect(screen.queryByText("coffer-mcp-shim")).not.toBeInTheDocument();
    expect(screen.queryByText(/disabled-one|codex-only/)).not.toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Manage: filesystem" })).not.toBeInTheDocument();
  });

  acceptance("agent-registry", "custom-tool groups have their own From Coffer row", async () => {
    stub({ servers: [...SERVERS.slice(0, 1), TOOL_GROUP] as typeof SERVERS });
    renderTab();
    expect(await screen.findByText("1 server through Coffer")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open MCP servers/ })).toHaveAttribute(
      "href",
      "/mcp-servers?agent=u-cc",
    );
    expect(screen.getByText("1 custom tool group through Coffer")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Custom tools/ })).toHaveAttribute(
      "href",
      "/custom-tools?agent=u-cc",
    );
    // The group is not counted among the servers.
    expect(screen.getByTestId("from-coffer-mcp")).not.toHaveTextContent("billing");
    expect(screen.getByTestId("from-coffer-custom-tools")).toHaveTextContent("billing");
  });

  test("the agent's own entries show command, file, secrets and state", async () => {
    stub();
    renderTab();
    await screen.findByRole("button", { name: "postgres-local" });

    const pg = rowOf("postgres-local");
    expect(within(pg).getByText("uvx mcp-server-postgres")).toBeInTheDocument();
    expect(within(pg).getByText("~/.claude.json")).toBeInTheDocument();
    expect(within(pg).getByText("1 secret in env")).toBeInTheDocument();
    expect(within(pg).getByText("Bypasses Coffer")).toBeInTheDocument();
    expect(within(pg).getByRole("button", { name: "Adopt: postgres-local" })).toBeInTheDocument();

    const gh = rowOf("github");
    expect(within(gh).getByText("Duplicate")).toBeInTheDocument();
    expect(within(gh).getByRole("link", { name: "github" })).toHaveAttribute(
      "href",
      "/mcp-servers/github",
    );
    expect(
      within(gh).getByRole("button", { name: "Remove duplicate: github" }),
    ).toBeInTheDocument();
  });

  test("the ⋯ menu holds Remove… only; a duplicate has none (its button removes it)", async () => {
    stub();
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "More for linear" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Remove…"]);
    expect(screen.queryByRole("button", { name: "More for github" })).toBeNull();
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Remove linear from ~/.claude.json?")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Claude Code loses this server in its next session. A backup copy is kept in Coffer’s folder, and nothing in Coffer changes.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(api.removeMcpEntry).toHaveBeenCalledWith("u-cc", "linear", "global"),
    );
  });

  acceptance("agent-registry", "open a direct MCP entry's JSON from the agent", async () => {
    stub();
    api.mcpEntry.mockResolvedValue({
      name: "postgres-local",
      source: "global",
      path: "/Users/me/.claude.json",
      transport: "stdio",
      config: { command: "uvx", args: ["mcp-server-postgres"], env: { DATABASE_URL: "••••••" } },
    } as never);
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "postgres-local" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.className).toContain("max-w-[640px]");
    expect(await within(dialog).findByText("From")).toBeInTheDocument();
    expect(within(dialog).getByText("~/.claude.json")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Copy JSON" })).toBeInTheDocument();
    // The footer Close (ghost) beside the corner ×.
    expect(within(dialog).getAllByRole("button", { name: "Close" })).toHaveLength(2);
    expect(within(dialog).getByRole("button", { name: "Remove" })).toBeInTheDocument();
    // Adopt goes on to the adopt dialog (the row's own flow).
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt" }));
    expect(await screen.findByText("Adopt postgres-local")).toBeInTheDocument();
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
    await screen.findByRole("button", { name: "Remove duplicate: github" });

    fireEvent.click(screen.getByRole("button", { name: "Remove duplicate: github" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Remove github from ~/.claude.json?")).toBeInTheDocument();
    api.mcpEntries.mockResolvedValue({ items: [GATEWAY, POSTGRES, LINEAR], parse_errors: [] });
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() =>
      expect(api.removeMcpEntry).toHaveBeenCalledWith("u-cc", "github", "global"),
    );
    // The server is now listed once: in Coffer's row, not among the agent's own entries.
    await waitFor(() => expect(screen.queryByRole("button", { name: "github" })).toBeNull());
    expect(screen.getByText("github · filesystem")).toBeInTheDocument();
  });

  test("a config file that failed to parse is an inline warning; its entries are read-only", async () => {
    stub({
      parse_errors: [
        { source: "global", path: "/Users/me/.claude.json", error: "Line 214, column 3" },
      ],
    });
    renderTab();
    expect(
      await screen.findByText(
        "Can’t read ~/.claude.json: Line 214, column 3. Its entries are read-only until the file is valid again.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Read-only")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Adopt: postgres-local" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove duplicate: github" })).toBeDisabled();
    vi.mocked(fsApi.open).mockResolvedValue(undefined);
    fireEvent.click(screen.getByRole("button", { name: "Open in editor" }));
    await waitFor(() =>
      expect(fsApi.open).toHaveBeenCalledWith("/Users/me/.claude.json", undefined),
    );
  });

  test("an agent with no MCP servers of its own shows the shared empty box", async () => {
    stub({ items: [GATEWAY], servers: [] });
    renderTab();
    expect(
      await screen.findByText("Claude Code has no MCP servers of its own"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Search servers")).toBeInTheDocument();
  });
});
