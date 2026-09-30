// src/pages/OverviewPage.test.tsx — the Overview: what needs you, each area's health, recent activity, first run.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import type { StreamMessage } from "@/lib/events/eventStream";
import { OverviewPage } from "./OverviewPage";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
vi.mock("@/lib/api/call", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/call")>()),
  call: vi.fn(),
}));
vi.mock("@/lib/events/eventStream", () => ({ followDaemonEvents: vi.fn() }));
// No real area carries an experimental feature, so the gate is tested by
// flagging the Knowledge tile with a test-only one.
vi.mock("@/lib/overview/health", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/overview/health")>();
  return {
    ...real,
    AREAS: real.AREAS.map((a) => (a.id === "knowledge" ? { ...a, feature: "fake_feature" } : a)),
  };
});

const { getApiClient } = await import("@/lib/api/client");
const { call } = await import("@/lib/api/call");
const { followDaemonEvents } = await import("@/lib/events/eventStream");

const now = Date.now();
const ago = (ms: number) => new Date(now - ms).toISOString();
const HOUR = 3_600_000;

interface Attention {
  items: unknown[];
  errors: { source: string; error: string }[];
  counts_by_kind: Record<string, number>;
}

const EMPTY_ATTENTION: Attention = { items: [], errors: [], counts_by_kind: {} };

const AGENTS = [
  { uid: "a-claude", type: "claude_code", name: "claude-code", display_name: "Claude Code" },
  { uid: "a-codex", type: "codex", name: "codex", display_name: "Codex" },
];

const action = (verb: string) => ({ verb, method: "POST", path: "/api/v1/x", body: null });

const ITEMS = [
  {
    kind: "agent",
    uid: "a-codex",
    title: "Codex",
    reason_code: "agent_not_connected",
    reason: "It is not connected to Coffer.",
    severity: "info",
    since: null,
    action: action("connect"),
  },
  {
    kind: "mcp_server",
    uid: "m-github",
    title: "github",
    reason_code: "mcp_failing",
    reason: "Its last connection test failed.",
    severity: "error",
    since: ago(2 * HOUR),
    action: action("test"),
  },
  {
    kind: "mcp_server",
    uid: "m-jira",
    title: "jira",
    reason_code: "mcp_missing_secret",
    reason: "The credential `jira_token` it uses is not stored on this machine.",
    severity: "error",
    since: ago(5 * HOUR),
    action: action("set_secret"),
  },
  {
    kind: "skill",
    uid: "s-review",
    title: "code-review",
    reason_code: "link_missing",
    reason: "Its link in Codex is missing.",
    severity: "warning",
    since: ago(HOUR),
    action: action("repair"),
  },
];

interface Setup {
  attention?: Attention | "fail";
  agents?: unknown[];
  features?: Record<string, boolean>;
  failing?: string[];
}

let state: Required<Setup>;
let listener: ((m: StreamMessage) => void) | null;

function ok(data: unknown) {
  return Promise.resolve({ data, error: undefined });
}
const FAIL = { error: { code: "INTERNAL_ERROR", message: "boom" } };

function install(setup: Setup = {}) {
  state = {
    attention: setup.attention ?? EMPTY_ATTENTION,
    agents: setup.agents ?? AGENTS,
    features: setup.features ?? { fake_feature: true },
    failing: setup.failing ?? [],
  };
  const get = vi
    .fn()
    .mockImplementation((path: string, init?: { params?: { query?: Record<string, unknown> } }) => {
      if (state.failing.includes(path)) return Promise.resolve({ data: undefined, error: FAIL });
      const query = init?.params?.query ?? {};
      switch (path) {
        case "/attention":
          return state.attention === "fail"
            ? Promise.resolve({ data: undefined, error: FAIL })
            : ok(state.attention);
        case "/daemon/status":
          return ok({ status: "ready", version: "0", port: 1, features: state.features });
        case "/resources":
          if (query.kind === "mcp_server") {
            return ok({
              resources: [
                { uid: "m-github", name: "github" },
                { uid: "m-jira", name: "jira" },
              ],
            });
          }
          if (query.kind === "channel")
            return ok({ resources: [{ uid: "c1", name: "seatalk", title: "SeaTalk" }] });
          return ok({ resources: [] });
        case "/mcp/invocations":
          return ok({
            invocations: [],
            next_cursor: null,
            total: query.status === "error" ? 23 : 1284,
          });
        case "/audit":
          return ok({
            entries: [
              {
                id: 1,
                timestamp: ago(60_000),
                event_type: "resource_created",
                resource_kind: "mcp_server",
                resource_name: "github",
                actor: "ui",
                details: null,
              },
            ],
            next_cursor: null,
            total: 1,
          });
        default:
          return ok(undefined);
      }
    });
  vi.mocked(getApiClient).mockReturnValue({ GET: get } as unknown as ReturnType<
    typeof getApiClient
  >);

  vi.mocked(call).mockImplementation((async (path: string) => {
    if (state.failing.includes(path)) throw new ApiError("INTERNAL_ERROR", "boom");
    switch (path) {
      case "/agents":
        return { items: state.agents };
      case "/agents/types":
        return {
          types: [
            { type: "claude_code", display_name: "Claude Code", state: "installed_active" },
            { type: "codex", display_name: "Codex", state: "missing" },
          ],
        };
      case "/providers":
        return { providers: [{ uid: "p1", name: "anthropic", title: "Anthropic" }] };
      case "/skills":
        return {
          items: [
            { uid: "s1", name: "code-review", bindings: [{ agent_uid: "a-claude" }] },
            { uid: "s2", name: "deploy", bindings: [{ agent_uid: "a-codex" }] },
          ],
        };
      case "/knowledge/collections":
        return { collections: [{ uid: "k1", name: "shopee", document_count: 142 }] };
      case "/memory/partitions":
        return { partitions: [{ uid: "mp1", name: "coffer", note_count: 9 }] };
      case "/sync/status":
        return {
          configured: true,
          last_run: { status: "ok" },
          remote: { url: "git@example:vault.git" },
        };
      default:
        throw new ApiError("NOT_FOUND", `unmocked ${path}`);
    }
  }) as typeof call);
  return get;
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false as never } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const needsYou = () => screen.getByRole("region", { name: "Needs you" });
const health = () => screen.getByRole("region", { name: "Health" });

beforeEach(() => {
  listener = null;
  vi.mocked(followDaemonEvents).mockImplementation(async (onMessage) => {
    listener = onMessage;
    onMessage({ type: "open" });
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("overview lists what needs the user, most severe first", () => {
  test("rows sort by severity then age, with reason, since and one action to the right page", async () => {
    install({ attention: { ...EMPTY_ATTENTION, items: ITEMS } });
    renderPage();
    await within(needsYou()).findByText("jira");
    const list = within(needsYou()).getByRole("list");
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((r) => within(r).getAllByRole("link")[0].textContent)).toEqual([
      expect.stringContaining("jira"),
      expect.stringContaining("github"),
      expect.stringContaining("code-review"),
      expect.stringContaining("Codex"),
    ]);

    const jira = rows[0];
    expect(within(jira).getByText(/jira_token/)).toBeInTheDocument();
    expect(within(jira).getByRole("img", { name: "Failing" })).toBeInTheDocument();
    expect(within(jira).getByRole("link", { name: /^Add secret/ })).toHaveAttribute(
      "href",
      "/secrets",
    );
    expect(within(jira).getByRole("link", { name: /^jira/ })).toHaveAttribute(
      "href",
      "/mcp-servers/m-jira",
    );
    expect(within(jira).getByText(/Since/)).toBeInTheDocument();

    expect(within(rows[1]).getByRole("link", { name: /^Test again/ })).toHaveAttribute(
      "href",
      "/mcp-servers/m-github",
    );
    expect(within(rows[2]).getByRole("link", { name: /^Repair drift/ })).toHaveAttribute(
      "href",
      "/skills/s-review",
    );
    const codex = rows[3];
    expect(within(codex).getByRole("img", { name: "Needs attention" })).toBeInTheDocument();
    expect(within(codex).getByRole("link", { name: /^Connect/ })).toHaveAttribute(
      "href",
      "/agents/a-codex",
    );
    // No since for an item that has none.
    expect(within(codex).queryByText(/Since/)).toBeNull();
  });

  test("a source that could not be checked says so above the rows", async () => {
    install({
      attention: {
        ...EMPTY_ATTENTION,
        items: ITEMS.slice(1, 2),
        errors: [{ source: "channel", error: "x" }],
      },
    });
    renderPage();
    expect(
      await screen.findByText(
        "Channels couldn't be checked, so anything it needs from you is missing from this list.",
      ),
    ).toBeInTheDocument();
    expect(within(needsYou()).getByText("github")).toBeInTheDocument();
    // A partial list is not "all good".
    expect(screen.queryByText("Nothing needs you")).toBeNull();
  });

  test("an attention read that fails entirely offers a retry", async () => {
    install({ attention: "fail" });
    renderPage();
    expect(await screen.findByText("Couldn't check what needs you")).toBeInTheDocument();
    expect(within(needsYou()).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("overview shows a calm card when nothing needs the user", () => {
  test("no items and no source errors read Nothing needs you, with the checked time", async () => {
    install();
    renderPage();
    expect(await screen.findByText("Nothing needs you")).toBeInTheDocument();
    expect(screen.getByText("Anything that needs you shows up here.")).toBeInTheDocument();
    // Healthy tiles are quiet; the numbers still read.
    const mcp = await within(health()).findByRole("link", { name: "MCP servers" });
    await waitFor(() => expect(mcp).toHaveTextContent("All answering"));
    expect(mcp).toHaveTextContent("2servers");
    await waitFor(() => expect(mcp).toHaveTextContent("1,284 calls · 23 errors in the last 24 h"));
    expect(screen.getByTestId("overview-live")).toHaveTextContent("Live");
    // Recent activity shows the last entry in the Activity page's words.
    const recent = screen.getByRole("region", { name: "Recent activity" });
    expect(await within(recent).findByText("github")).toBeInTheDocument();
    expect(within(recent).getByRole("link", { name: "Open Activity" })).toHaveAttribute(
      "href",
      "/activity",
    );
  });
});

describe("overview welcomes a first run with the agents to connect", () => {
  test("no agents: the first-run panel replaces Needs you and Health", async () => {
    install({ agents: [] });
    renderPage();
    expect(await screen.findByText("Connect your coding agents")).toBeInTheDocument();
    expect(await screen.findByText("Found on this Mac")).toBeInTheDocument();
    expect(screen.getByText("Not installed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Review and connect/ })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(screen.getByRole("link", { name: "Add MCP server" })).toHaveAttribute(
      "href",
      "/mcp-servers",
    );
    expect(screen.queryByRole("region", { name: "Needs you" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Health" })).toBeNull();
  });
});

describe("one area failing to load leaves the rest of overview working", () => {
  test("the Skills tile shows its error while the other tiles render", async () => {
    install({ failing: ["/skills"] });
    renderPage();
    const skills = await within(health()).findByRole("group", { name: "Skills" });
    expect(within(skills).getByText("Couldn't load")).toBeInTheDocument();
    expect(within(skills).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(skills).getByRole("link", { name: "Open Skills" })).toHaveAttribute(
      "href",
      "/skills",
    );
    const providers = await within(health()).findByRole("link", { name: "Model providers" });
    await waitFor(() => expect(providers).toHaveTextContent("Anthropic"));
    expect(await screen.findByText("Nothing needs you")).toBeInTheDocument();
  });
});

describe("overview hides an area whose backend or feature is off", () => {
  test("a switched-off feature has no tile; custom tools and CLIs never have one", async () => {
    install({ features: { fake_feature: false } });
    renderPage();
    const region = health();
    expect(await within(region).findByRole("link", { name: "Memory" })).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: "Sync" })).toBeInTheDocument();
    expect(within(region).queryByRole("link", { name: "Knowledge" })).toBeNull();
    expect(within(region).queryByRole("link", { name: "Custom tools" })).toBeNull();
    expect(within(region).queryByRole("link", { name: "CLIs" })).toBeNull();
  });
});

describe("a resolved problem leaves overview on its own", () => {
  test("an attention change on the event stream refetches the list", async () => {
    const get = install({ attention: { ...EMPTY_ATTENTION, items: ITEMS.slice(1, 2) } });
    renderPage();
    expect(await within(needsYou()).findByText("github")).toBeInTheDocument();
    const attentionReads = () => get.mock.calls.filter((c) => c[0] === "/attention").length;
    const before = attentionReads();

    state.attention = EMPTY_ATTENTION;
    await waitFor(() => expect(listener).not.toBeNull());
    act(() => {
      listener?.({
        type: "change",
        change: { seq: 1, kind: "attention", id: null, rev: null, op: "upsert" },
      });
    });
    expect(await screen.findByText("Nothing needs you")).toBeInTheDocument();
    expect(attentionReads()).toBeGreaterThan(before);
    expect(within(needsYou()).queryByText("github")).toBeNull();
  });
});
