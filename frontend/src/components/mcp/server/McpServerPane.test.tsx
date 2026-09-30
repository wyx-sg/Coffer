// src/components/mcp/server/McpServerPane.test.tsx — the open MCP server: its state, why, who calls it, its tools, its log, delete.
//
// revise-web-ui-ia: mcp-gateway "Explain a server's state on its page" and
// "Read a server's own log from its page" (the page half) — the acceptance
// markers are added when the change is archived.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { ResourceOut } from "@/lib/api/resources";
import { McpServerPane } from "./McpServerPane";

const api = vi.hoisted(() => ({
  status: {} as Record<string, unknown>,
  summary: {
    since: "",
    calls: 0,
    errors: 0,
    last_call_at: null,
    by_agent: [],
    by_tool: [],
  } as Record<string, unknown>,
  tiering: {
    enabled: true,
    budget: 50,
    catalogue_size: 3,
    listed_count: 3,
    tool_count: 3,
    listed: [],
    behind_search: [],
  } as Record<string, unknown>,
  log: { path: "/logs/upstream/duckdb.log", lines: [], truncated: false } as Record<
    string,
    unknown
  >,
  invocations: [] as unknown[],
  post: vi.fn(),
}));

const TOOLS = ["list_issues", "get_issue", "search_events", "resolve_issue", "create_issue"].map(
  (n, i) => ({
    prefixed_name: `sentry__${n}`,
    original_name: n,
    description: `${n} description`,
    input_schema: {},
    enabled: i !== 4,
    client_name_length: 20,
  }),
);

vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({
    GET: vi.fn(async (path: string) => {
      if (path.endsWith("/status")) return { data: { status: "unknown", ...api.status } };
      if (path.endsWith("/invocations/summary")) return { data: api.summary };
      if (path.endsWith("/tiering")) return { data: api.tiering };
      if (path.endsWith("/log")) return { data: api.log };
      if (path.endsWith("/capabilities"))
        return {
          data: {
            server_name: "sentry",
            tools: TOOLS,
            resources: [],
            prompts: [],
            fetched_at: "",
            from_cache: false,
          },
        };
      if (path.endsWith("/invocations"))
        return {
          data: { invocations: api.invocations, next_cursor: null, total: api.invocations.length },
        };
      return { data: undefined, error: { error: { code: "NOT_FOUND", message: path } } };
    }),
    POST: api.post,
  }),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({
    data: [
      { uid: "a-cc", type: "claude_code", display_name: "Claude Code" },
      { uid: "a-cx", type: "codex", display_name: "Codex" },
    ],
  }),
}));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: "SENTRY_TOKEN",
          present: true,
          cited_by: [{ uid: "u-sentry", kind: "mcp_server", name: "sentry" }],
        },
        { ref: "SHARED", present: true, cited_by: [{ uid: "u-sentry" }, { uid: "u-other" }] },
      ],
    })),
    remove: vi.fn(async () => undefined),
  },
}));
vi.mock("@/lib/api/resources", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/resources")>()),
  resourcesApi: {
    remove: vi.fn(async () => undefined),
    enable: vi.fn(async () => undefined),
    disable: vi.fn(async () => undefined),
  },
}));
vi.mock("@/components/mcp/EditMcpServerDialog", () => ({
  EditMcpServerDialog: ({ focus }: { focus?: string }) => (
    <div role="dialog">{`edit dialog ${focus ?? ""}`}</div>
  ),
}));
vi.mock("@/components/ScopeControl", () => ({ ScopeControl: () => <button>Every agent</button> }));

const { secretsApi } = await import("@/lib/api/secret");
const { resourcesApi } = await import("@/lib/api/resources");

const SENTRY = {
  uid: "u-sentry",
  name: "sentry",
  kind: "mcp_server",
  title: "Sentry",
  enabled: true,
  scope: null,
  config: {
    transport: {
      type: "http",
      url: "https://mcp.sentry.dev/mcp",
      headers: {},
      secret_refs: { Authorization: "SENTRY_TOKEN", "X-Shared": "SHARED" },
    },
  },
} as unknown as ResourceOut;

const DUCKDB = {
  ...SENTRY,
  uid: "u-duck",
  name: "duckdb",
  title: null,
  config: { transport: { type: "stdio", command: "uvx", args: ["mcp-server-duckdb"] } },
} as unknown as ResourceOut;

function renderPane(resource: ResourceOut = SENTRY, path = `/mcp-servers/${resource.name}`) {
  const onDeleted = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route
                path="/mcp-servers/:name/:tab?"
                element={
                  <McpServerPane
                    resource={resource}
                    basePath={`/mcp-servers/${resource.name}`}
                    onDeleted={onDeleted}
                  />
                }
              />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return { onDeleted };
}

describe("McpServerPane", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.status = {};
    api.summary = { since: "", calls: 0, errors: 0, last_call_at: null, by_agent: [], by_tool: [] };
    api.tiering = {
      enabled: true,
      budget: 50,
      catalogue_size: 3,
      listed_count: 3,
      tool_count: 5,
      listed: [],
      behind_search: [],
    };
    api.invocations = [];
  });

  test("a failing server says its last error, since when and its last success, with View log", async () => {
    api.status = {
      status: "failing",
      last_error: "Connection refused by mcp.sentry.dev",
      last_error_at: new Date().toISOString(),
      failing_since: new Date().toISOString(),
      last_ok_at: new Date().toISOString(),
      last_ok_capability: "list_issues",
    };
    renderPane();
    const callout = await screen.findByTestId("mcp-callout-failing");
    expect(within(callout).getByText("Connection refused by mcp.sentry.dev")).toBeInTheDocument();
    expect(callout).toHaveTextContent(/failing since/);
    expect(callout).toHaveTextContent(/Last successful call .*list_issues/);
    expect(callout).toHaveTextContent(/Claude Code, Codex can't call its 5 tools/);
    expect(screen.getByText("Failing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /test again/i })).toBeInTheDocument();
    fireEvent.click(within(callout).getByRole("button", { name: /view log/i }));
    expect(await screen.findByTestId("mcp-log-drawer")).toBeInTheDocument();
  });

  test("a missing launcher names the command that installs it", async () => {
    api.status = { status: "failing", missing_runner: "uvx" };
    renderPane(DUCKDB);
    const callout = await screen.findByTestId("mcp-callout-launcher");
    expect(within(callout).getByText("uvx is not installed on this Mac")).toBeInTheDocument();
    expect(within(callout).getByText("brew install uv")).toBeInTheDocument();
  });

  test("a secret missing on this Mac is named and offers Replace secret", async () => {
    api.status = {
      status: "healthy",
      missing_secret: "Authorization",
      missing_secret_ref: "SENTRY_TOKEN",
    };
    renderPane();
    const callout = await screen.findByTestId("mcp-callout-secret");
    expect(
      within(callout).getByText(/the secret SENTRY_TOKEN isn't in this Mac's keychain/i),
    ).toBeInTheDocument();
    fireEvent.click(within(callout).getByRole("button", { name: /replace secret/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("edit dialog secret");
  });

  test("an Off server explains itself and offers Turn on", async () => {
    renderPane({ ...SENTRY, enabled: false } as ResourceOut);
    expect(await screen.findByTestId("mcp-callout-off")).toHaveTextContent(/no agent can use it/i);
    fireEvent.click(screen.getAllByRole("button", { name: /turn on/i })[0]);
    await waitFor(() => expect(resourcesApi.enable).toHaveBeenCalledWith("u-sentry"));
  });

  test("the Overview shows who it reaches, the last 24 hours by agent, and the busiest tools", async () => {
    api.summary = {
      since: "",
      calls: 312,
      errors: 41,
      last_call_at: new Date().toISOString(),
      by_agent: [
        { agent_uid: "a-cc", calls: 201, errors: 30, last_call_at: new Date().toISOString() },
        { agent_uid: null, calls: 3, errors: 0, last_call_at: null },
      ],
      by_tool: [{ tool: "get_issue", calls: 96, errors: 12, last_call_at: null }],
    };
    api.tiering = {
      ...api.tiering,
      listed: ["list_issues"],
      behind_search: ["get_issue", "search_events"],
    };
    renderPane();
    expect(await screen.findByTestId("mcp-24h-totals")).toHaveTextContent("312 calls");
    expect(screen.getByTestId("mcp-24h-totals")).toHaveTextContent("41 errors");
    const calledBy = screen.getByRole("table", { name: /called by/i });
    expect(within(calledBy).getByText("201")).toBeInTheDocument();
    expect(within(calledBy).getByText(/session that named no agent/i)).toBeInTheDocument();
    expect(screen.getByText(/Most behind search · 1 listed · 2 by search/)).toBeInTheDocument();
    expect(screen.getByText("Reach is set on this Mac only")).toBeInTheDocument();
    expect(await screen.findByTestId("mcp-callout-tiering")).toBeInTheDocument();
    // Busiest first, four shown, the rest one link away.
    const tools = await screen.findByRole("list", { name: "Tools" });
    expect(within(tools).getAllByRole("listitem")[0]).toHaveTextContent("get_issue");
    expect(screen.getByRole("link", { name: /show 1 more/i })).toHaveAttribute(
      "href",
      "/mcp-servers/sentry/tools",
    );
  });

  test("All off turns every tool that is on off, one call each", async () => {
    api.post.mockResolvedValue({ data: undefined, error: undefined, response: { status: 204 } });
    renderPane(SENTRY, "/mcp-servers/sentry/tools");
    expect(await screen.findByTestId("mcp-tools-on")).toHaveTextContent("4 of 5 on");
    fireEvent.click(screen.getByRole("button", { name: /all off/i }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(4));
    expect(api.post.mock.calls[0][0]).toBe(
      "/resources/mcp_server/{uid}/capabilities/{capability_type}/disable",
    );
  });

  test("the log drawer reads the calls and the server's own log, each line saying who wrote it", async () => {
    api.status = { status: "failing", missing_runner: "uvx" };
    api.invocations = [
      {
        id: 1,
        timestamp: new Date().toISOString(),
        capability_key: "query",
        capability_type: "tool",
        agent_uid: "a-cc",
        status: "error",
        duration_ms: 3000,
        error_message: "Connection refused",
        session_id: "s1",
        resource_uid: "u-duck",
        resource_name: "duckdb",
      },
    ];
    api.log = {
      path: "/logs/upstream/duckdb.log",
      truncated: false,
      lines: [
        {
          text: 'error launcher "uvx" not found on PATH /usr/bin',
          source: "coffer",
          at: new Date().toISOString(),
        },
        { text: "Installed 14 packages", source: "stderr", at: null },
      ],
    };
    renderPane(DUCKDB);
    fireEvent.click(await screen.findByRole("button", { name: /more actions for duckdb/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /calls and server log/i }));
    const drawer = await screen.findByTestId("mcp-log-drawer");
    expect(await within(drawer).findByText("query")).toBeInTheDocument();
    fireEvent.click(within(drawer).getByText("query"));
    expect(within(drawer).getByTestId("mcp-call-detail")).toHaveTextContent("Connection refused");
    expect(within(drawer).getByText(/never the arguments or the result/i)).toBeInTheDocument();
    fireEvent.mouseDown(within(drawer).getByRole("tab", { name: /server log/i }));
    const log = await within(drawer).findByTestId("mcp-server-log");
    expect(log).toHaveTextContent('error launcher "uvx" not found');
    expect(log).toHaveTextContent("stderr");
  });

  test("an HTTP server's drawer says it has no server log", async () => {
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /calls and server log/i }));
    const drawer = await screen.findByTestId("mcp-log-drawer");
    fireEvent.mouseDown(within(drawer).getByRole("tab", { name: /server log/i }));
    expect(await within(drawer).findByText(/has no log of its own/i)).toBeInTheDocument();
  });

  test("Copy config as JSON carries the secret names, never a value", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /copy config as json/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const copied = JSON.parse(writeText.mock.calls[0][0]);
    expect(copied.sentry.transport.secret_refs.Authorization).toBe("SENTRY_TOKEN");
  });

  test("Delete says what it costs and can take the secrets only this server uses", async () => {
    const { onDeleted } = renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /delete/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete sentry?")).toBeInTheDocument();
    expect(within(dialog).getByText(/Claude Code, Codex lose its 5 tools/)).toBeInTheDocument();
    // Only the secret nobody else cites is offered.
    const box = await within(dialog).findByRole("checkbox", {
      name: /also delete the secret SENTRY_TOKEN/i,
    });
    fireEvent.click(box);
    fireEvent.click(within(dialog).getByRole("button", { name: /delete server/i }));
    await waitFor(() => expect(resourcesApi.remove).toHaveBeenCalledWith("u-sentry"));
    await waitFor(() => expect(secretsApi.remove).toHaveBeenCalledWith("SENTRY_TOKEN"));
    expect(secretsApi.remove).not.toHaveBeenCalledWith("SHARED");
    expect(onDeleted).toHaveBeenCalled();
  });
});
