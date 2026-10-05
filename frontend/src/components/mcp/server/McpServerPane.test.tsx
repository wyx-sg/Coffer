// src/components/mcp/server/McpServerPane.test.tsx — the open MCP server: its state, why, who calls it, its tools, its log, delete.
//
// The page half of spec mcp-gateway "Explain a server's state on its page" and
// "Read a server's own log from its page"; the routes' scenarios are marked on
// backend/tests/integration/surfaces/http/mcp/test_page_routes.py.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { actionLabelKey } from "@/lib/overview/attention";
import { acceptance } from "@/test/acceptance";
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
  gets: [] as { path: string; query: unknown }[],
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

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({
    GET: vi.fn(async (path: string, init?: { params?: { query?: unknown } }) => {
      api.gets.push({ path, query: init?.params?.query });
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
            from_cache: (init?.params?.query as { saved?: boolean } | undefined)?.saved === true,
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
const { SENTRY_REF, SHARED_REF } = vi.hoisted(() => ({
  SENTRY_REF: `secret/${"d4".repeat(16)}`,
  SHARED_REF: `secret/${"e5".repeat(16)}`,
}));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: SENTRY_REF,
          label: "Sentry token",
          present: true,
          cited_by: [{ uid: "u-sentry", kind: "mcp_server", name: "sentry" }],
          mentioned_by_skills: [],
          bindings: [],
        },
        {
          ref: SHARED_REF,
          label: "Shared key",
          present: true,
          cited_by: [{ uid: "u-sentry" }, { uid: "u-other" }],
          mentioned_by_skills: [],
          bindings: [],
        },
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
  EditMcpServerDialog: () => <div role="dialog">edit dialog</div>,
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
      secret_refs: { Authorization: SENTRY_REF, "X-Shared": SHARED_REF },
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

function ActivityProbe() {
  const { pathname, search } = useLocation();
  return <div data-testid="activity-probe">{pathname + search}</div>;
}

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
              <Route path="/activity" element={<ActivityProbe />} />
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
    api.gets = [];
  });

  acceptance(
    "web-ui",
    "a failing HTTP server says why and offers View errors, not a log",
    async () => {
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
      expect(callout).toHaveTextContent(/Claude Code and Codex can't call its 5 tools/);
      expect(screen.getByText("Failing")).toBeInTheDocument();
      // The header never changes with the state: Test, not Test again.
      expect(screen.getByRole("button", { name: "Test" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /test again/i })).toBeNull();
      // A server Coffer does not start has no log: View errors opens Activity on its failed calls.
      expect(within(callout).queryByRole("button", { name: /view log/i })).toBeNull();
      fireEvent.click(within(callout).getByRole("button", { name: /view errors/i }));
      expect(await screen.findByTestId("activity-probe")).toHaveTextContent(
        "/activity?tab=mcp&q=sentry&status=failed",
      );
    },
  );

  acceptance("web-ui", "the 24-hour block opens the server's own call history", async () => {
    renderPane();
    const link = await screen.findByRole("link", { name: "View in Activity" });
    expect(link).toHaveAttribute("href", "/activity?tab=mcp&q=sentry");
    fireEvent.click(link);
    expect(await screen.findByTestId("activity-probe")).toHaveTextContent(
      "/activity?tab=mcp&q=sentry",
    );
  });

  acceptance("web-ui", "a failing stdio server opens its Server log", async () => {
    api.status = { status: "failing", last_error: "exited with status 1" };
    renderPane(DUCKDB);
    const callout = await screen.findByTestId("mcp-callout-failing");
    fireEvent.click(within(callout).getByRole("button", { name: /view log/i }));
    expect(await screen.findByTestId("mcp-log-drawer")).toBeInTheDocument();
  });

  acceptance("web-ui", "a rejected key reads Replace key", async () => {
    api.status = { status: "failing", failure_reason: "auth_rejected" };
    renderPane();
    const callout = await screen.findByTestId("mcp-callout-key-rejected");
    expect(callout).toHaveTextContent("The key was rejected");
    expect(callout).toHaveTextContent(/rejected with 401 Unauthorized/);
    fireEvent.click(within(callout).getByRole("button", { name: "Replace key" }));
    expect(await screen.findByText("edit dialog")).toBeInTheDocument();
    expect(actionLabelKey("replace_key")).toBe("overview.actions.replace_key");
  });

  acceptance(
    "web-ui",
    "a missing launcher offers the hand-off, not an install command",
    async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", {
        value: { writeText },
        configurable: true,
        writable: true,
      });
      const prompt =
        "Please install `uvx` on this machine so Coffer can start the MCP server duckdb.";
      api.status = { status: "failing", missing_runner: "uvx", handoff: { prompt } };
      renderPane(DUCKDB);
      const callout = await screen.findByTestId("mcp-callout-launcher");
      expect(within(callout).getByText("uvx isn't found on this machine")).toBeInTheDocument();
      expect(callout).not.toHaveTextContent(/brew/);
      fireEvent.click(within(callout).getByRole("button", { name: "Copy prompt" }));
      await waitFor(() => expect(writeText).toHaveBeenCalledWith(prompt));
    },
  );

  acceptance("web-ui", "a failed test offers a diagnosis hand-off beside View log", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });
    const prompt =
      "Please find out why the MCP server sentry, which Coffer runs for my agents, fails.";
    api.post.mockResolvedValue({
      data: {
        ok: false,
        latency_ms: 812,
        error_message: "Connection refused by mcp.sentry.dev",
        error_code: "connect_failed",
        exit_code: null,
        protocol_version: null,
        server_capabilities: null,
        tools: [],
        tool_count: 0,
        resource_count: null,
        prompt_count: null,
        stderr_tail: [],
        unreleased_secret_keys: [],
        handoff: { prompt },
      },
      error: undefined,
    });
    api.status = { status: "healthy" };
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /^test$/i }));
    const result = await screen.findByTestId("mcp-test-result");
    expect(result).toHaveTextContent("Connection refused by mcp.sentry.dev");
    expect(within(result).getByRole("button", { name: /view errors/i })).toBeInTheDocument();
    fireEvent.click(within(result).getByRole("button", { name: "Copy prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(prompt));
    expect(screen.getByRole("button", { name: "Test" })).toBeInTheDocument();
  });

  test("a failing server offers its diagnosis hand-off beside View errors", async () => {
    api.status = {
      status: "failing",
      last_error: "exited with status 1",
      handoff: { prompt: "Please find out why the MCP server sentry fails." },
    };
    renderPane();
    const callout = await screen.findByTestId("mcp-callout-failing");
    expect(within(callout).getByRole("button", { name: /view errors/i })).toBeInTheDocument();
    expect(within(callout).getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
  });

  test("a secret missing on this Mac is named and offers Add secret, the Secrets dialog", async () => {
    api.status = {
      status: "healthy",
      missing_secret: "Authorization",
      missing_secret_ref: SENTRY_REF,
      label: "Sentry token",
    };
    renderPane();
    const callout = await screen.findByTestId("mcp-callout-secret");
    expect(
      within(callout).getByText(/Authorization isn.t in this Mac.s keychain/i),
    ).toBeInTheDocument();
    expect(callout).toHaveTextContent(/Secrets don.t travel with a restored vault/);
    // No Credentials section any more.
    expect(screen.queryByText("Credentials")).toBeNull();
    fireEvent.click(within(callout).getByRole("button", { name: "Add secret" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Sentry token");
    expect(dialog).not.toHaveTextContent("edit dialog");
  });

  acceptance("web-ui", "an Off server explains itself and offers Turn on", async () => {
    renderPane({ ...SENTRY, enabled: false } as ResourceOut);
    expect(await screen.findByTestId("mcp-callout-off")).toHaveTextContent(/no agent can use it/i);
    fireEvent.click(screen.getAllByRole("button", { name: /turn on/i })[0]);
    await waitFor(() => expect(resourcesApi.enable).toHaveBeenCalledWith("u-sentry"));
  });

  acceptance(
    "web-ui",
    "the Overview stacks the last 24 hours by agent, what it requires and the busiest tools",
    async () => {
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
      api.status = {
        status: "healthy",
        requires: [
          { kind: "cli", name: "npx", status: "found", version: "10.9.2", secret: null },
          {
            kind: "secret",
            name: "Authorization",
            status: "missing",
            version: null,
            secret: "sentry.AUTH_TOKEN",
          },
        ],
      };
      renderPane();
      expect(await screen.findByTestId("mcp-24h-totals")).toHaveTextContent("312 calls");
      expect(screen.getByTestId("mcp-24h-totals")).toHaveTextContent("41 errors");
      expect(
        screen.getByText("Calls your agents made to sentry, and how many failed."),
      ).toBeVisible();
      const calledBy = screen.getByRole("table", { name: /called by/i });
      expect(within(calledBy).getByText("201")).toBeInTheDocument();
      expect(within(calledBy).getByText(/session that named no agent/i)).toBeInTheDocument();
      // No Agents section, no tiering banner: banner → Last 24 hours → Requires → Most-called tools.
      expect(screen.queryByText("Reach is set on this Mac only")).toBeNull();
      expect(screen.queryByTestId("mcp-callout-tiering")).toBeNull();
      expect(await screen.findByText("Found · 10.9.2")).toBeInTheDocument();
      expect(screen.getByText("View in CLIs")).toHaveAttribute("href", "/clis/npx");
      expect(screen.getByText("Missing")).toBeInTheDocument();
      // A secret row names the secret, not the header that carries it.
      expect(screen.getByText("Authorization")).toBeInTheDocument();
      expect(screen.queryByText("View in Secrets")).toBeNull();
      expect(screen.getByRole("button", { name: /replace key/i })).toBeInTheDocument();
      // Busiest first, four shown, read-only (no switches), the rest one link away.
      const tools = await screen.findByRole("table", { name: "Most-called tools" });
      const rows = within(tools).getAllByRole("row");
      // A header row, then four tools.
      expect(rows).toHaveLength(5);
      expect(rows[1]).toHaveTextContent("get_issue");
      expect(rows[1]).toHaveTextContent("Behind search");
      expect(within(tools).queryByRole("switch")).toBeNull();
      expect(screen.getByRole("link", { name: /show all 5 in tools/i })).toHaveAttribute(
        "href",
        "/mcp-servers/sentry/tools",
      );
    },
  );

  test("an Off server's last 24 hours says only its last call; its header menu has no Turn off", async () => {
    api.summary = {
      since: "",
      calls: 0,
      errors: 0,
      last_call_at: null,
      by_agent: [{ agent_uid: "a-cx", calls: 4, errors: 0, last_call_at: "2026-09-20T09:00:00Z" }],
      by_tool: [],
    };
    renderPane({ ...SENTRY, enabled: false } as ResourceOut);
    expect(await screen.findByTestId("mcp-24h-off")).toHaveTextContent(
      /No calls while off\. Last call Sep 20, by Codex\./,
    );
    expect(screen.queryByTestId("mcp-24h-totals")).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    expect(screen.queryByRole("menuitem", { name: "Turn off" })).toBeNull();
  });

  test("Tools tab rows open to one column ending in the last call and who made it", async () => {
    api.summary = {
      since: "",
      calls: 5,
      errors: 0,
      last_call_at: new Date().toISOString(),
      by_agent: [],
      by_tool: [{ tool: "get_issue", calls: 5, errors: 0, last_call_at: new Date().toISOString() }],
    };
    api.invocations = [
      {
        id: 1,
        timestamp: new Date().toISOString(),
        capability_key: "get_issue",
        capability_type: "tool",
        agent_uid: "a-cx",
        status: "ok",
        duration_ms: 300,
        error_message: null,
        session_id: null,
        resource_uid: "u-sentry",
        resource_name: "sentry",
      },
    ];
    renderPane(SENTRY, "/mcp-servers/sentry/tools");
    const table = await screen.findByRole("table", { name: "Tools" });
    fireEvent.click(within(table).getByText("get_issue"));
    const detail = within(table).getByTestId("mcp-tool-detail");
    expect(detail).toHaveTextContent("mcp__coffer__sentry__get_issue");
    await waitFor(() => expect(detail).toHaveTextContent(/Last call .* by Codex/));
    expect(detail).not.toHaveTextContent("calls ·");
  });

  test("selecting all tools and choosing Turn off turns every tool that is on off, one call each", async () => {
    api.post.mockResolvedValue({ data: undefined, error: undefined, response: { status: 204 } });
    renderPane(SENTRY, "/mcp-servers/sentry/tools");
    await screen.findByRole("table", { name: "Tools" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all" }));
    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(4));
    expect(api.post.mock.calls[0][0]).toBe(
      "/resources/mcp_server/{uid}/capabilities/{capability_type}/disable",
    );
  });

  test("the Server log drawer has no tabs and each line says who wrote it", async () => {
    api.status = { status: "failing", missing_runner: "uvx" };
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
    fireEvent.click(screen.getByRole("menuitem", { name: "Server log" }));
    const drawer = await screen.findByTestId("mcp-log-drawer");
    expect(within(drawer).getByText("duckdb · Server log")).toBeInTheDocument();
    expect(within(drawer).queryByRole("tab")).toBeNull();
    const log = await within(drawer).findByTestId("mcp-server-log");
    expect(log).toHaveTextContent('error launcher "uvx" not found');
    expect(log).toHaveTextContent("stderr");
  });

  test("the ⋯ menu of a stdio server: Server log · Copy config as JSON · Turn off · Delete…", async () => {
    renderPane(DUCKDB);
    fireEvent.click(await screen.findByRole("button", { name: /more actions for duckdb/i }));
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Server log", "Copy config as JSON", "Turn off", "Delete…"]);
  });

  acceptance("web-ui", "an HTTP server's menu has no Server log", async () => {
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Copy config as JSON", "Turn off", "Delete…"]);
  });

  test("Turn off says so in a toast with Undo, which turns it back on", async () => {
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Turn off" }));
    await waitFor(() => expect(resourcesApi.disable).toHaveBeenCalledWith("u-sentry"));
    expect(await screen.findByText("sentry turned off")).toBeInTheDocument();
    expect(screen.getByText("Its settings and the agents you chose are kept.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(resourcesApi.enable).toHaveBeenCalledWith("u-sentry"));
  });

  test("Copy config as JSON carries the secret names, never a value", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /copy config as json/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const copied = JSON.parse(writeText.mock.calls[0][0]);
    expect(copied.sentry.transport.secret_refs.Authorization).toBe(SENTRY_REF);
  });

  acceptance("web-ui", "Delete server says what it costs and offers its own secret", async () => {
    const { onDeleted } = renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /delete/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete sentry?")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Claude Code and Codex lose its 5 tools on their next call. Its call history stays in Activity.",
      ),
    ).toBeVisible();
    // Only a secret no other server uses can go with it; unticked by default.
    const box = await within(dialog).findByRole("checkbox");
    expect(box).not.toBeChecked();
    expect(within(dialog).getByText("Sentry token")).toBeInTheDocument();
    expect(within(dialog).getByText("No other server uses it.")).toBeInTheDocument();
    expect(within(dialog).queryByText("Shared key")).toBeNull();
    expect(within(dialog).getByText(/This can.t be undone/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /delete server/i }));
    await waitFor(() => expect(resourcesApi.remove).toHaveBeenCalledWith("u-sentry"));
    expect(secretsApi.remove).not.toHaveBeenCalled();
    expect(onDeleted).toHaveBeenCalled();
  });

  test("ticking Also delete the secret removes it after the server", async () => {
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /delete/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("checkbox"));
    fireEvent.click(within(dialog).getByRole("button", { name: /delete server/i }));
    await waitFor(() => expect(secretsApi.remove).toHaveBeenCalledWith(SENTRY_REF));
  });

  acceptance("web-ui", "a refused delete stays open under its error title", async () => {
    vi.mocked(resourcesApi.remove).mockRejectedValueOnce(new Error("in use"));
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /more actions for sentry/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /delete/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /delete server/i }));
    expect(await within(dialog).findByText("Couldn’t delete sentry")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  test("a failing server's header is tinted, and its tools come from the saved switches at once", async () => {
    api.status = { status: "failing", last_ok_at: new Date().toISOString() };
    renderPane();
    await waitFor(() =>
      expect(screen.getByTestId("mcp-server-tile")).toHaveAttribute("data-state", "failing"),
    );
    expect(screen.getByTestId("mcp-server-target")).toHaveTextContent(
      "Streamable HTTP · https://mcp.sentry.dev/mcp",
    );
    await screen.findByRole("table", { name: "Most-called tools" });
    const reads = api.gets.filter((g) => g.path.endsWith("/capabilities"));
    expect(reads.length).toBeGreaterThan(0);
    expect(reads.every((g) => (g.query as { saved?: boolean } | undefined)?.saved === true)).toBe(
      true,
    );
    expect(screen.getByText(/From the last successful connection, at/)).toBeInTheDocument();
    // The callout sits inside the Overview tab, under the tab row.
    const overview = screen.getByRole("tabpanel");
    expect(within(overview).getByTestId("mcp-callout-failing")).toBeInTheDocument();
  });

  test("with no agent to name, a failing server's sentence still reads", async () => {
    api.status = { status: "failing" };
    renderPane({ ...SENTRY, scope: { agents: ["not-registered-here"] } } as unknown as ResourceOut);
    const callout = await screen.findByTestId("mcp-callout-failing");
    expect(callout).toHaveTextContent(/Agents can't call its 5 tools until it answers again/);
  });

  test("a test that passed is a toast, not a box in the Overview", async () => {
    api.post.mockResolvedValue({
      data: {
        ok: true,
        latency_ms: 1234,
        error_message: null,
        error_code: null,
        exit_code: 0,
        protocol_version: null,
        server_capabilities: null,
        tools: [],
        tool_count: 26,
        resource_count: null,
        prompt_count: 0,
        stderr_tail: ["server ready"],
        unreleased_secret_keys: [],
      },
      error: undefined,
    });
    api.status = { status: "healthy" };
    renderPane();
    fireEvent.click(await screen.findByRole("button", { name: /^test$/i }));
    expect(await screen.findByText("Test passed · 26 tools")).toBeInTheDocument();
    expect(screen.getByText("The same set agents see now.")).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-test-result")).toBeNull();
  });

  test("the Tools tab lists every tool with Search tools, the first ten shown", async () => {
    renderPane(SENTRY, "/mcp-servers/sentry/tools");
    const table = await screen.findByRole("table", { name: "Tools" });
    expect(within(table).getAllByRole("row")).toHaveLength(TOOLS.length + 1);
    fireEvent.change(screen.getByPlaceholderText("Search tools"), {
      target: { value: "resolve" },
    });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
  });
});
