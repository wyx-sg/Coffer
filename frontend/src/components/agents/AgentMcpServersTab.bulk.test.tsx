// src/components/agents/AgentMcpServersTab.bulk.test.tsx — acting on several of the agent's own MCP entries at once.
//
// Covered: an entry of a file that failed to parse taking no checkbox; Adopt
// sending each bypassing entry's default body (its own name, default secret
// references) one after another and saying how many secret values move; a name
// conflict failing that entry alone; Remove… naming entries and files and
// removing each from its source file; a duplicate being skipped by Adopt.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentMcpServersTab } from "./AgentMcpServersTab";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import type { McpEntryOut } from "@/lib/api/agents-workspace";
import { getApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import { mockApiClient } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
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
  effort: null,
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

const POSTGRES = entry("postgres-local", {
  env_keys: ["DATABASE_URL"],
  secret_keys: ["DATABASE_URL"],
});
const LINEAR = entry("linear");
const GITHUB_COPY = entry("github", { matches_resource: "github" });
const BROKEN_FILE = entry("stale", { source: "project" });

function stub() {
  vi.mocked(getApiClient).mockReturnValue(
    mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: { resources: [] }, error: undefined }),
    }) as unknown as ReturnType<typeof getApiClient>,
  );
  api.mcpEntries.mockResolvedValue({
    items: [POSTGRES, LINEAR, GITHUB_COPY, BROKEN_FILE],
    parse_errors: [{ source: "project", path: "/Users/me/p/.mcp.json", error: "bad json" }],
  });
  api.listConfigFiles.mockResolvedValue({
    items: [{ key: "global", path: "/Users/me/.claude.json" }],
  } as Awaited<ReturnType<typeof agentsApi.listConfigFiles>>);
  api.removeMcpEntry.mockResolvedValue(undefined);
  api.adoptMcpEntry.mockResolvedValue({ uid: "r-1", kind: "mcp_server", name: "x" });
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <AgentMcpServersTab agent={AGENT} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const tick = (name: string) =>
  fireEvent.click(screen.getByRole("checkbox", { name: `Select ${name}` }));
const bar = () => screen.getByRole("region", { name: "Selected servers" });

afterEach(() => vi.clearAllMocks());

describe("AgentMcpServersTab — bulk", () => {
  acceptance(
    "agent-registry",
    "adopt or remove several of the agent's own MCP entries at once",
    async () => {
      stub();
      renderTab();
      await screen.findByRole("button", { name: "postgres-local" });
      // The entry of the unreadable file is read-only: no checkbox.
      expect(screen.queryByRole("checkbox", { name: "Select stale" })).toBeNull();

      tick("postgres-local");
      tick("linear");
      fireEvent.click(within(bar()).getByRole("button", { name: "Adopt" }));
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText("Adopt 2 servers?")).toBeInTheDocument();
      expect(
        within(dialog).getByText(/1 secret value moves into Coffer’s secret store/),
      ).toBeInTheDocument();
      fireEvent.click(within(dialog).getByRole("button", { name: "Adopt 2 servers" }));
      await waitFor(() => expect(api.adoptMcpEntry).toHaveBeenCalledTimes(2));
      expect(api.adoptMcpEntry.mock.calls).toEqual([
        [
          "u-cc",
          "postgres-local",
          {
            source: "global",
            secrets: { DATABASE_URL: "mcp/claude_code/postgres-local/DATABASE_URL" },
          },
        ],
        ["u-cc", "linear", { source: "global" }],
      ]);
      expect(await screen.findByText(/Adopted 2 servers/)).toBeInTheDocument();
      await waitFor(() =>
        expect(screen.queryByRole("region", { name: "Selected servers" })).toBeNull(),
      );

      // Remove… names each entry and its file, then removes each from its source file.
      tick("linear");
      tick("github");
      fireEvent.click(within(bar()).getByRole("button", { name: "Remove…" }));
      const confirm = await screen.findByRole("dialog");
      expect(within(confirm).getByText("Remove 2 servers?")).toBeInTheDocument();
      expect(within(confirm).getByText("linear")).toBeInTheDocument();
      expect(within(confirm).getAllByText("~/.claude.json")).toHaveLength(2);
      fireEvent.click(within(confirm).getByRole("button", { name: "Remove 2 servers" }));
      await waitFor(() => expect(api.removeMcpEntry).toHaveBeenCalledTimes(2));
      expect(api.removeMcpEntry.mock.calls).toEqual([
        ["u-cc", "linear", "global"],
        ["u-cc", "github", "global"],
      ]);
    },
  );

  test("Adopt skips a duplicate and says so; a name Coffer has fails that entry alone", async () => {
    stub();
    api.adoptMcpEntry.mockRejectedValueOnce(new ApiError("RESOURCE_ALREADY_EXISTS", "name taken"));
    renderTab();
    await screen.findByRole("button", { name: "postgres-local" });
    tick("postgres-local");
    tick("linear");
    tick("github");
    fireEvent.click(within(bar()).getByRole("button", { name: "Adopt" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/1 selected entry is skipped: only entries that bypass Coffer/),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt 2 servers" }));
    const alert = await within(dialog).findByRole("alert");
    expect(within(alert).getByText("Adopted 1 of 2")).toBeInTheDocument();
    expect(within(alert).getByText("postgres-local")).toBeInTheDocument();
    expect(api.adoptMcpEntry).toHaveBeenCalledTimes(2);
    expect(within(dialog).getByRole("button", { name: "Retry 1 that failed" })).toBeInTheDocument();
  });
});
