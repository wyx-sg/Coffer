// frontend/src/pages/ResourcesPage.test.tsx
//
// The MCP servers page: the list beside the open server. It scopes its query
// to kind=mcp_server SERVER-SIDE rather than fetching every resource and
// filtering client-side (which once leaked memory and knowledge stores into
// this list). The data hooks are mocked at the network boundary.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";
import { ResourcesPage } from "./ResourcesPage";

vi.mock("@/lib/hooks/useResources", () => ({ useResources: vi.fn() }));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => ({ live: false }) }));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({
    data: [
      { uid: "a-cc", type: "claude_code", display_name: "Claude Code" },
      { uid: "a-cx", type: "codex", display_name: "Codex" },
    ],
  }),
}));
// The agents' own MCP entries Coffer does not serve; none unless a test sets them.
const direct: { groups: unknown[]; count: number } = { groups: [], count: 0 };
vi.mock("@/lib/hooks/useAgentDirectMcpEntries", () => ({
  useAgentDirectMcpEntries: () => ({ ...direct, isLoading: false }),
}));
vi.mock("@/components/mcp/AddMcpServerDialog", () => ({
  AddMcpServerDialog: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">add dialog</div> : null,
}));
vi.mock("@/components/mcp/server/McpServerPane", () => ({
  McpServerPane: ({ resource }: { resource: ResourceOut }) => (
    <div data-testid="pane">{`pane: ${resource.name}`}</div>
  ),
}));

// Coffer's own server, as `GET /mcp/builtin` describes it; off unless a test sets it.
const builtin: { data: unknown } = { data: undefined };
vi.mock("@/lib/hooks/useMcpAddFlow", () => ({
  useBuiltinMcpServer: () => ({ data: builtin.data, isPending: false }),
  useMcpImportPlan: () => ({ data: undefined, isPending: false }),
}));

const statusOf: Record<string, unknown> = {};
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({
    GET: vi.fn(async (path: string, opts: { params: { path: { uid: string } } }) => {
      if (path === "/secrets")
        return {
          data: {
            refs: [
              {
                ref: "LINEAR_API_KEY",
                label: "Linear key",
                present: false,
                cited_by: [],
                mentioned_by_skills: [],
                bindings: [],
              },
            ],
          },
        };
      const uid = opts.params.path.uid;
      if (path.endsWith("/status")) return { data: statusOf[uid] ?? { status: "unknown" } };
      if (path.endsWith("/tiering"))
        return {
          data: {
            enabled: true,
            budget: 50,
            catalogue_size: 3,
            listed_count: 3,
            tool_count: 3,
            listed: ["a", "b", "c"],
            behind_search: [],
          },
        };
      return { data: undefined, error: { error: { code: "NOT_FOUND", message: "x" } } };
    }),
  }),
}));

const { useResources } = await import("@/lib/hooks/useResources");
const useResourcesMock = vi.mocked(useResources);

function server(uid: string, name: string, extra: Partial<ResourceOut> = {}): ResourceOut {
  return {
    uid,
    name,
    kind: "mcp_server",
    title: null,
    enabled: true,
    scope: null,
    config: { transport: { type: "stdio", command: "npx", args: ["-y", name] } },
    ...extra,
  } as unknown as ResourceOut;
}

function stubQuery(opts: { data?: ResourceOut[]; isPending?: boolean; error?: unknown }) {
  useResourcesMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useResources>);
}

const where = { url: "" };
function Probe() {
  const loc = useLocation();
  where.url = loc.pathname + loc.search;
  return null;
}

function renderAt(path = "/mcp-servers") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              {["/mcp-servers", "/mcp-servers/:name", "/mcp-servers/:name/:tab"].map((p) => (
                <Route
                  key={p}
                  path={p}
                  element={
                    <>
                      <ResourcesPage />
                      <Probe />
                    </>
                  }
                />
              ))}
              <Route path="*" element={<Probe />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("ResourcesPage", () => {
  beforeEach(() => {
    for (const k of Object.keys(statusOf)) delete statusOf[k];
    builtin.data = undefined;
  });
  afterEach(() => vi.clearAllMocks());

  test("scopes the query to mcp_server (does not list every kind)", () => {
    stubQuery({ data: [] });
    renderAt();
    expect(useResourcesMock).toHaveBeenCalledWith("mcp_server");
  });

  test("keeps the header up over skeleton rows while the query is pending", () => {
    stubQuery({ isPending: true });
    renderAt();
    expect(screen.getByRole("heading", { name: /mcp servers/i })).toBeInTheDocument();
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    // Seven two-line rows, the shape of the real ones; the right pane stays empty.
    expect(document.querySelectorAll('[aria-busy="true"] > .h-\\[52px\\]')).toHaveLength(7);
  });

  acceptance("web-ui", "a server error never reads as an unexpected error", () => {
    stubQuery({ error: new ApiError("INTERNAL_ERROR", "internal error") });
    const { container } = renderAt();
    expect(screen.getByText(/couldn.t load mcp servers/i)).toBeInTheDocument();
    // A readable message that says where to look, not a shrug.
    expect(screen.getByText(/activity/i)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/unexpected error/i);
    expect(container.textContent).not.toContain("INTERNAL_ERROR");
  });

  acceptance("web-ui", "a failed list shows its error block in the list pane", () => {
    const error = new ApiError("INTERNAL_ERROR", "internal error", undefined, {
      status: 500,
      path: "/api/v1/resources?kind=mcp_server",
      trace: "01J9Z4K2QX",
    });
    stubQuery({ error });
    renderAt();
    // The header and the filter stay; the block sits in the list pane.
    expect(screen.getByRole("heading", { name: /mcp servers/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Filter servers" })).toBeInTheDocument();
    const block = screen.getByRole("alert");
    expect(within(block).getByText("Couldn’t load MCP servers")).toBeInTheDocument();
    expect(block).toHaveTextContent("Nothing was changed.");
    expect(block).toHaveTextContent(
      "GET /api/v1/resources?kind=mcp_server · 500 · trace 01J9Z4K2QX",
    );
    fireEvent.click(within(block).getByRole("button", { name: "Retry" }));
    fireEvent.click(within(block).getByRole("button", { name: "Open daemon log" }));
    expect(where.url).toBe("/activity?tab=daemon");
  });

  acceptance(
    "web-ui",
    "a filter that matches nothing names the filter and offers Clear filter",
    () => {
      stubQuery({ data: [server("u1", "github")] });
      renderAt();
      const filter = screen.getByRole("textbox", { name: "Filter servers" });
      fireEvent.change(filter, { target: { value: "terraform" } });
      expect(screen.getByText("No server matches “terraform”")).toBeInTheDocument();
      expect(screen.getByText("Filters names, titles, commands and URLs.")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Clear filter" }));
      expect(filter).toHaveValue("");
      expect(screen.getByRole("link", { name: /github/ })).toBeInTheDocument();
    },
  );

  acceptance("web-ui", "a detail whose object is gone says so and leads back", async () => {
    stubQuery({ data: [server("u1", "github")] });
    renderAt("/mcp-servers/sentry-old");
    expect(
      await screen.findByRole("heading", { level: 1, name: "This server no longer exists" }),
    ).toBeInTheDocument();
    expect(screen.getByText("sentry-old")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to MCP servers" })).toHaveAttribute(
      "href",
      "/mcp-servers",
    );
    expect(screen.getByRole("link", { name: "View in Activity" })).toHaveAttribute(
      "href",
      "/activity?tab=changes",
    );
  });

  acceptance("web-ui", "empty resources list renders a welcome view", () => {
    stubQuery({ data: [] });
    renderAt();
    const welcome = screen.getByTestId("mcp-welcome");
    expect(within(welcome).getByText(/no mcp servers yet/i)).toBeInTheDocument();
    // The welcome repeats no Add; the page header's button opens the dialog.
    expect(within(welcome).queryByRole("button", { name: /add server/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /add server/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("add dialog");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  test("the welcome sends each agent's own servers to that agent's MCP servers tab", () => {
    direct.groups = [
      {
        agent: { uid: "a-cc", type: "claude_code", display_name: "Claude Code" },
        entries: [{ name: "jira" }],
        duplicates: [],
      },
    ];
    direct.count = 1;
    try {
      stubQuery({ data: [] });
      renderAt();
      const found = screen.getByTestId("mcp-welcome-found");
      expect(within(found).getByRole("link", { name: /claude code/i })).toHaveAttribute(
        "href",
        "/agents/claude_code/mcp-servers",
      );
      // Importing is done on the agent's page; the welcome offers no import of its own.
      expect(within(found).queryByRole("button")).toBeNull();
    } finally {
      direct.groups = [];
      direct.count = 0;
    }
  });

  // The dialog half (no Import from agents link, no custom tool) is
  // AddMcpServerDialog.test.tsx.
  acceptance("web-ui", "the add dialog offers no import from agents", () => {
    stubQuery({ data: [server("u1", "github")] });
    renderAt();
    // Only the page header holds Add; the Nothing selected pane has none.
    const adds = screen.getAllByRole("button", { name: /add server/i });
    expect(adds).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /paste json|import json/i })).toBeNull();
  });

  test("the list groups servers by what needs the user, each with its reason", async () => {
    statusOf.u1 = {
      status: "failing",
      last_error: "Connection refused",
      failing_since: new Date().toISOString(),
    };
    statusOf.u2 = {
      status: "healthy",
      missing_secret: "Authorization",
      missing_secret_ref: "LINEAR_API_KEY",
    };
    statusOf.u3 = { status: "failing", missing_runner: "uvx" };
    statusOf.u4 = { status: "healthy" };
    stubQuery({
      data: [
        server("u1", "sentry"),
        server("u2", "linear"),
        server("u3", "duckdb"),
        server("u4", "github", { scope: { agents: ["a-cc"] } } as Partial<ResourceOut>),
        server("u5", "postgres", { enabled: false }),
      ],
    });
    renderAt();
    const attention = await screen.findByRole("region", { name: "Needs attention" });
    await within(attention).findByText(/Connection refused · since/);
    expect(await within(attention).findByText("Secret missing · Linear key")).toBeInTheDocument();
    expect(within(attention).getByText("uvx isn't found on this machine")).toBeInTheDocument();
    const healthy = screen.getByRole("region", { name: "Healthy" });
    expect(within(healthy).getByText("github")).toBeInTheDocument();
    await within(healthy).findByText("stdio · 3 tools");
    const off = screen.getByRole("region", { name: "Off" });
    expect(within(off).getByText("postgres")).toBeInTheDocument();
  });

  // Base-spec scenario: the row is a link, so a click or Enter opens the item.
  acceptance("web-ui", "a row click opens the item's detail page", async () => {
    stubQuery({ data: [server("u1", "github"), server("u2", "linear")] });
    renderAt("/mcp-servers/github/tools");
    expect(await screen.findByTestId("pane")).toHaveTextContent("pane: github");
    fireEvent.click(screen.getByRole("link", { name: /linear/ }));
    // The open tab is kept when another server is chosen.
    expect(where.url).toBe("/mcp-servers/linear/tools");
    await waitFor(() => expect(screen.getByTestId("pane")).toHaveTextContent("pane: linear"));
  });

  test("filtering narrows the list by name or command", async () => {
    stubQuery({ data: [server("u1", "github"), server("u2", "linear")] });
    renderAt();
    fireEvent.change(screen.getByRole("textbox", { name: /filter servers/i }), {
      target: { value: "lin" },
    });
    expect(screen.queryByText("github")).toBeNull();
    expect(screen.getByText("linear")).toBeInTheDocument();
  });

  test("the list has the search and a Reach filter", () => {
    stubQuery({ data: [server("u1", "github")] });
    renderAt();
    expect(screen.getByRole("combobox", { name: "Reach" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /filter servers/i })).toBeInTheDocument();
  });

  test("several ticked servers: the right pane says how many and offers Turn off N servers", async () => {
    stubQuery({
      data: [server("u1", "github"), server("u2", "linear"), server("u3", "sentry")],
    });
    renderAt();
    fireEvent.click(screen.getByRole("checkbox", { name: /github/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /linear/ }));
    expect(await screen.findByText("2 servers selected")).toBeInTheDocument();
    expect(screen.getByText(/github and linear\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn off 2 servers" })).toBeInTheDocument();
  });

  test("ticking rows shows the selection bar with the reach choice and Delete", async () => {
    stubQuery({ data: [server("u1", "github"), server("u2", "linear")] });
    renderAt();
    fireEvent.click(screen.getByRole("checkbox", { name: /github/ }));
    const bar = screen.getByRole("region", { name: /selected mcp servers/i });
    expect(within(bar).getByRole("button", { name: /reach/i })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: /delete/i })).toBeInTheDocument();
  });
  // The scenario's custom-tool AND: a custom-tool group (an http_api server) is
  // not on the MCP servers page; SidebarNav.test.tsx has the entries half.
  acceptance("web-ui", "each listed resource kind has one sidebar entry", () => {
    const group = server("u-ct", "billing", {
      config: { transport: { type: "http_api", base_url: "https://billing.example" } },
    } as unknown as Partial<ResourceOut>);
    stubQuery({ data: [group, server("u-gh", "github")] });
    renderAt();
    expect(screen.getByText("github")).toBeInTheDocument();
    expect(screen.queryByText("billing")).toBeNull();
  });

  acceptance(
    "web-ui",
    "the built-in coffer server is listed last and opens read-only",
    async () => {
      builtin.data = {
        name: "coffer",
        invocation_uid: "coffer",
        transport: "http",
        url: "http://127.0.0.1:38470/mcp",
        status: "healthy",
        checked_at: new Date().toISOString(),
        reaches_all_connected_agents: true,
        connected_agent_uids: ["a-cc"],
        tool_count: 1,
        tools: [
          { name: "search_tools", qualified_name: "coffer__search_tools", description: "Find" },
        ],
        summary: {
          calls: 0,
          errors: 0,
          last_call_at: null,
          since: new Date().toISOString(),
          by_agent: [],
          by_tool: [],
        },
      };
      stubQuery({ data: [server("u-gh", "github")] });
      renderAt("/mcp-servers/coffer");
      const groups = screen.getAllByRole("region").map((r) => r.getAttribute("aria-label"));
      expect(groups[groups.length - 1]).toBe("Built-in");
      expect(
        within(screen.getByRole("region", { name: "Built-in" })).queryByRole("checkbox"),
      ).toBeNull();
      // The pane is lazy-loaded; a cold CI worker can take over a second to import it.
      expect(
        await screen.findByTestId("mcp-builtin-pane", {}, { timeout: 5000 }),
      ).toBeInTheDocument();
      expect(screen.getByText("coffer__search_tools", { exact: false })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^(Test|Edit)$/ })).toBeNull();
      expect(screen.getAllByText("All agents").length).toBeGreaterThan(0);
    },
  );

  test("a custom-tool group's MCP server address opens its Custom tools page", async () => {
    const group = server("u-ct", "billing", {
      config: { transport: { type: "http_api", base_url: "https://billing.example" } },
    } as unknown as Partial<ResourceOut>);
    stubQuery({ data: [group] });
    renderAt("/mcp-servers/billing/tools");
    await waitFor(() => expect(where.url).toBe("/custom-tools/billing"));
  });
});
