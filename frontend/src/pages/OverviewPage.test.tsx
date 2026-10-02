// src/pages/OverviewPage.test.tsx — the Overview: what needs you, each area's health, recent activity, first run.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import type { StreamMessage } from "@/lib/events/eventStream";
import { OverviewPage } from "./OverviewPage";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/events/eventStream", () => ({ followDaemonEvents: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");
const { followDaemonEvents } = await import("@/lib/events/eventStream");

const ALL_ON = { knowledge: true, memory: true, sync: true, models: true };
const ALL_OFF = { knowledge: false, memory: false, sync: false, models: false };

const now = Date.now();
const ago = (ms: number) => new Date(now - ms).toISOString();
const HOUR = 3_600_000;

type AttentionRow = { key?: string } & Record<string, unknown>;

interface Attention {
  items: AttentionRow[];
  errors: { source: string; error: string }[];
  counts_by_kind: Record<string, number>;
  ignored?: AttentionRow[];
}

const EMPTY_ATTENTION: Attention = { items: [], errors: [], counts_by_kind: {} };

const AGENTS = [
  { uid: "a-claude", type: "claude_code", name: "claude-code", display_name: "Claude Code" },
  { uid: "a-codex", type: "codex", name: "codex", display_name: "Codex" },
];

const action = (verb: string) => ({ verb, method: "POST", path: "/api/v1/x", body: null });

const ITEMS = [
  {
    key: "agent:a-codex:agent_not_connected",
    ignorable: true,
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
    reason: "The secret `jira_token` it uses is not stored on this machine.",
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
  /** "one-found": Claude Code on this Mac, Codex not; "none-found": neither. */
  types?: "one-found" | "none-found";
}

let state: Required<Setup>;
/** The routes the page read that the typed-client mock answers by its fallback table. */
let routed: string[] = [];
let routeFallback: (path: string) => unknown = () => undefined;
let listener: ((m: StreamMessage) => void) | null;

function ok(data: unknown) {
  return Promise.resolve({ data, error: undefined });
}
const FAIL = { error: { code: "INTERNAL_ERROR", message: "boom" } };

function install(setup: Setup = {}) {
  routed = [];
  state = {
    attention: setup.attention ?? EMPTY_ATTENTION,
    agents: setup.agents ?? AGENTS,
    features: setup.features ?? ALL_ON,
    failing: setup.failing ?? [],
    types: setup.types ?? "one-found",
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
        case "/custom-tools":
          return ok({
            groups: [
              { uid: "g1", name: "billing", calls_24h: 31, failures_24h: 0, health: "healthy" },
            ],
          });
        case "/clis":
          return ok({
            items: [
              { command: "gh", status: "ready", needed_by: [{ skill_uid: "s1" }] },
              { command: "jq", status: "ready", needed_by: [{ skill_uid: "s2" }] },
            ],
            warnings: [],
          });
        case "/usage/summary":
          return ok({
            totals: {
              input_tokens: 1_500_000,
              output_tokens: 600_000,
              estimated_cost_usd: 4.12,
              requests: 10,
              unpriced_requests: 0,
            },
            rows: [
              {
                key: "m1",
                connection_name: "Anthropic",
                totals: { input_tokens: 1_000_000, output_tokens: 500_000 },
              },
              {
                key: "m2",
                connection_name: "Acme gateway",
                totals: { input_tokens: 500_000, output_tokens: 100_000 },
              },
            ],
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
          try {
            routed.push(path);
            return ok(routeFallback(path));
          } catch (e) {
            const err = e as ApiError;
            return Promise.resolve({
              data: undefined,
              error: { error: { code: err.code, message: err.envelopeMessage } },
              response: { status: 404 },
            });
          }
      }
    });
  // The daemon keeps what is ignored: PUT moves an item from `items` to
  // `ignored`, DELETE moves it back.
  const move = (key: string, toIgnored: boolean) => {
    if (state.attention === "fail") return;
    const from = toIgnored ? state.attention.items : (state.attention.ignored ?? []);
    const item = from.find((i) => i.key === key);
    if (!item) return;
    const rest = from.filter((i) => i !== item);
    state.attention = toIgnored
      ? { ...state.attention, items: rest, ignored: [...(state.attention.ignored ?? []), item] }
      : { ...state.attention, ignored: rest, items: [...state.attention.items, item] };
  };
  const keyed =
    (toIgnored: boolean) => (_path: string, init: { params: { path: { key: string } } }) => {
      move(init.params.path.key, toIgnored);
      return Promise.resolve({ data: undefined, error: undefined });
    };
  vi.mocked(getApiClient).mockReturnValue({
    GET: get,
    PUT: vi.fn().mockImplementation(keyed(true)),
    DELETE: vi.fn().mockImplementation(keyed(false)),
  } as unknown as ReturnType<typeof getApiClient>);

  const routes = (path: string): unknown => {
    switch (path) {
      case "/agents":
        return { items: state.agents };
      case "/agents/types":
        return {
          types: [
            {
              type: "claude_code",
              display_name: "Claude Code",
              config_dir: "/Users/me/.claude",
              state: state.types === "none-found" ? "missing" : "installed_active",
            },
            {
              type: "codex",
              display_name: "Codex",
              config_dir: "/Users/me/.codex",
              state: "missing",
            },
          ],
          install_handoff:
            state.types === "none-found"
              ? {
                  prompt:
                    "Please install Claude Code or Codex on this Mac, so Coffer can connect it.",
                }
              : null,
        };
      case "/agent-providers":
        return { agents: [] };
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
      case "/secrets":
        return {
          refs: [
            {
              ref: "gh_token",
              present: true,
              unreferenced: false,
              bindings: [{ destination_kind: "mcp_server", destination_uid: "m-github" }],
              cited_by: [],
              mentioned_by_skills: [],
            },
            {
              ref: "old_token",
              present: true,
              unreferenced: true,
              bindings: [],
              cited_by: [],
              mentioned_by_skills: [],
            },
          ],
        };
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
  };
  routeFallback = routes;
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
  acceptance("web-ui", "overview lists what needs the user, most severe first", async () => {
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
      "/mcp-servers/jira",
    );
    expect(within(jira).getByText(/Since/)).toBeInTheDocument();

    expect(within(rows[1]).getByRole("link", { name: /^Test again/ })).toHaveAttribute(
      "href",
      "/mcp-servers/github",
    );
    expect(within(rows[2]).getByRole("link", { name: /^Repair drift/ })).toHaveAttribute(
      "href",
      "/skills/code-review",
    );
    const codex = rows[3];
    expect(within(codex).getByRole("img", { name: "Needs attention" })).toBeInTheDocument();
    expect(within(codex).getByRole("link", { name: /^Connect/ })).toHaveAttribute(
      "href",
      "/agents/codex",
    );
    // No since for an item that has none.
    expect(within(codex).queryByText(/Since/)).toBeNull();
  });

  test("a long needs-you list scrolls inside its own window", async () => {
    const many = Array.from({ length: 20 }, (_, i) => ({
      ...ITEMS[0],
      uid: `m-${i}`,
      title: `srv-${i}`,
    }));
    install({ attention: { ...EMPTY_ATTENTION, items: many } });
    renderPage();
    await within(needsYou()).findByText("srv-0");
    const list = screen.getByTestId("needs-you-scroll");
    expect(list).toHaveClass("overflow-y-auto");
    expect(list.className).toMatch(/max-h-/);
    expect(within(list).getAllByRole("listitem")).toHaveLength(20);
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
  acceptance("web-ui", "overview shows a calm card when nothing needs the user", async () => {
    install();
    renderPage();
    expect(await screen.findByText("Nothing needs you")).toBeInTheDocument();
    expect(screen.getByText("Anything that needs you shows up here.")).toBeInTheDocument();
    expect(needsYou().querySelector("time")).not.toBeNull();
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
  acceptance("web-ui", "overview welcomes a first run with the agents to connect", async () => {
    install({ agents: [] });
    renderPage();
    expect(await screen.findByText("Connect your coding agents")).toBeInTheDocument();
    expect(await screen.findByText(/^Coffer found 1 agent on this Mac\./)).toBeInTheDocument();
    expect(screen.getByText("Found on this Mac")).toBeInTheDocument();
    expect(screen.getByText("Not found")).toBeInTheDocument();
    // Only a found agent can be ticked; it starts ticked.
    expect(screen.getByRole("checkbox", { name: "Connect Claude Code" })).toBeChecked();
    expect(screen.queryByRole("checkbox", { name: "Connect Codex" })).toBeNull();
    expect(screen.getByRole("button", { name: "Review and connect 1 agent" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Add an agent by hand" })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(screen.getByRole("link", { name: "Add MCP server" })).toHaveAttribute(
      "href",
      "/mcp-servers",
    );
    expect(screen.queryByRole("region", { name: "Needs you" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Health" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Recent activity" })).toBeNull();
  });

  test("with no agent found the first step is scanning again", async () => {
    install({ agents: [], types: "none-found" });
    renderPage();
    expect(await screen.findByText("No coding agents found")).toBeInTheDocument();
    expect(screen.getAllByText("Not found")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Scan again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Review and connect/ })).toBeNull();
  });

  acceptance(
    "web-ui",
    "with no agent found overview offers the install prompt to copy",
    async () => {
      install({ agents: [], types: "none-found" });
      renderPage();
      expect(await screen.findByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
      // There is no agent to ask, and no installer link of Coffer's own.
      expect(screen.queryByRole("button", { name: /ask an agent/i })).toBeNull();
      expect(screen.queryByRole("link", { name: /install/i })).toBeNull();
    },
  );
});

describe("one area failing to load leaves the rest of overview working", () => {
  acceptance("web-ui", "one area failing to load leaves the rest of overview working", async () => {
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

/** Every request the page made to a route of one of the four experimental features. */
function gatedRequests(get: ReturnType<typeof install>): string[] {
  const GATED = /^\/(providers|models|proxy|usage|knowledge|memory|sync)(\/|$)/;
  const KINDS = new Set(["provider", "knowledge", "memory"]);
  const viaClient = get.mock.calls
    .filter(([path, init]) => {
      const kind = (init as { params?: { query?: { kind?: string } } } | undefined)?.params?.query
        ?.kind;
      return GATED.test(path as string) || (path === "/resources" && KINDS.has(kind ?? ""));
    })
    .map(([path]) => path as string);
  const viaCall = routed.filter((path) => GATED.test(path));
  return [...viaClient, ...viaCall];
}

describe("overview hides an area whose backend or feature is off", () => {
  acceptance("web-ui", "overview hides an area whose backend or feature is off", async () => {
    const get = install({ features: ALL_OFF });
    renderPage();
    const region = health();
    const tools = await within(region).findByRole("link", { name: "Custom tools" });
    // Only the always-on areas have a tile while every feature is off.
    for (const name of ["Knowledge", "Memory", "Model providers", "Sync", "Usage"]) {
      expect(within(region).queryByRole("link", { name })).toBeNull();
    }
    await waitFor(() => expect(tools).toHaveTextContent("31 requests · 0 errors in the last 24 h"));
    const clis = within(region).getByRole("link", { name: "CLIs" });
    await waitFor(() => expect(clis).toHaveTextContent("Needed by 2 skills · gh, jq"));
    const secrets = within(region).getByRole("link", { name: "Secrets" });
    await waitFor(() => expect(secrets).toHaveTextContent("1 unused"));
    const names = within(region)
      .getAllByRole("link")
      .map((a) => a.getAttribute("aria-label"));
    expect(names).toEqual([
      "Agents",
      "MCP servers",
      "Skills",
      "Channels",
      "Custom tools",
      "CLIs",
      "Secrets",
    ]);
    // Nothing of a switched-off feature was asked for, so nothing can have failed.
    expect(gatedRequests(get)).toEqual([]);
  });

  test("with every feature on, each area has its tile", async () => {
    install();
    renderPage();
    const region = health();
    expect(await within(region).findByRole("link", { name: "Memory" })).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: "Sync" })).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: "Knowledge" })).toBeInTheDocument();
    const usage = within(region).getByRole("link", { name: "Usage" });
    await waitFor(() => expect(usage).toHaveTextContent("Anthropic 71%"));
    expect(usage).toHaveTextContent("$4.12");
    // Board order: what agents use first, then the system areas.
    const names = within(region)
      .getAllByRole("link")
      .map((a) => a.getAttribute("aria-label"));
    expect(names.slice(-4)).toEqual(["Custom tools", "CLIs", "Secrets", "Usage"]);
  });

  test("one feature off hides only its own tiles and requests", async () => {
    const get = install({ features: { ...ALL_ON, models: false } });
    renderPage();
    const region = health();
    expect(await within(region).findByRole("link", { name: "Memory" })).toBeInTheDocument();
    expect(within(region).queryByRole("link", { name: "Model providers" })).toBeNull();
    expect(within(region).queryByRole("link", { name: "Usage" })).toBeNull();
    expect(within(region).getByRole("link", { name: "Knowledge" })).toBeInTheDocument();
    expect(gatedRequests(get).filter((p) => /providers|usage|proxy|models/.test(p))).toEqual([]);
  });

  test("the first-run panel offers only the areas whose feature is on", async () => {
    const get = install({ agents: [], types: "none-found", features: ALL_OFF });
    renderPage();
    const then = (await screen.findByRole("heading", { name: "Then add what they share" })).closest(
      "section",
    )!;
    expect(within(then).getByText("MCP servers")).toBeInTheDocument();
    expect(within(then).getByText("Skills")).toBeInTheDocument();
    expect(within(then).getByText("Channels")).toBeInTheDocument();
    for (const name of ["Knowledge", "Model providers"]) {
      expect(within(then).queryByText(name)).toBeNull();
    }
    expect(gatedRequests(get)).toEqual([]);
  });
});

describe("a resolved problem leaves overview on its own", () => {
  acceptance("web-ui", "a resolved problem leaves overview on its own", async () => {
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
        change: { seq: 1, kind: "attention", id: null, op: "upsert" },
      });
    });
    expect(await screen.findByText("Nothing needs you")).toBeInTheDocument();
    expect(attentionReads()).toBeGreaterThan(before);
    expect(within(needsYou()).queryByText("github")).toBeNull();
  });
});

const HOOK_ITEM = {
  kind: "agent",
  uid: "a-claude",
  title: "Claude Code",
  reason_code: "stale_command",
  reason:
    "Coffer's memory hook in this agent's settings no longer matches what Coffer installs (its command changed).",
  severity: "warning",
  since: ago(HOUR),
  action: {
    verb: "repair",
    method: "POST",
    path: "/api/v1/reconcile/apply",
    body: { ids: ["delivery_hook:a-claude"] },
  },
};

acceptance(
  "web-ui",
  "a memory hook changed by hand opens the agent's hooks tab from overview",
  async () => {
    install({ attention: { ...EMPTY_ATTENTION, items: [HOOK_ITEM] } });
    renderPage();
    const name = await within(needsYou()).findByText("Claude Code");
    const row = name.closest("li") as HTMLElement;
    expect(within(row).getByText(/no longer matches what Coffer installs/)).toBeInTheDocument();
    expect(within(row).getByText(/Since/)).toBeInTheDocument();
    // One action, on the agent's Hooks tab; the name still opens the agent.
    expect(within(row).getAllByRole("link")).toHaveLength(2);
    expect(within(row).getByRole("link", { name: /^Repair hook/ })).toHaveAttribute(
      "href",
      "/agents/claude_code/hooks",
    );
    expect(within(row).getByRole("link", { name: /^Claude Code/ })).toHaveAttribute(
      "href",
      "/agents/claude_code",
    );
    // Not an item that can be ignored: no menu.
    expect(within(row).queryByRole("button", { name: /More for/ })).toBeNull();
  },
);

acceptance("web-ui", "an ignored agent leaves needs you and is counted under it", async () => {
  install({ attention: { ...EMPTY_ATTENTION, items: [ITEMS[0], ITEMS[1]] } });
  renderPage();
  await within(needsYou()).findByText("Codex");
  fireEvent.click(within(needsYou()).getByRole("button", { name: "More for Codex" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Ignore" }));

  await waitFor(() => expect(within(needsYou()).queryByText("Codex")).toBeNull());
  expect(within(needsYou()).getByText("github")).toBeInTheDocument();
  expect(within(needsYou()).getByText(/1 ignored/)).toBeInTheDocument();

  // Show lists it again, muted, with Stop ignoring.
  fireEvent.click(within(needsYou()).getByRole("button", { name: "Show" }));
  const ignored = within(needsYou()).getByRole("list", { name: "Ignored" });
  expect(within(ignored).getByText("Codex")).toBeInTheDocument();
  fireEvent.click(within(ignored).getByRole("button", { name: "More for Codex" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Stop ignoring" }));
  await waitFor(() => expect(within(needsYou()).queryByText(/ignored/)).toBeNull());
  expect(within(needsYou()).getByText("Codex")).toBeInTheDocument();
});

acceptance("web-ui", "overview flags a required CLI that needs attention", async () => {
  const outdated = {
    kind: "cli",
    uid: "gh",
    title: "gh",
    reason_code: "cli_outdated",
    reason: "gh 2.30.0 is older than 2.40, needed by gh-triage.",
    severity: "warning",
    since: null,
    action: { verb: "check", method: "POST", path: "/api/v1/clis/gh/check", body: null },
  };
  install({ attention: { ...EMPTY_ATTENTION, items: [outdated] } });
  renderPage();
  const name = await within(needsYou()).findByText("gh");
  const row = name.closest("li") as HTMLElement;
  expect(within(row).getByText(/older than 2\.40/)).toBeInTheDocument();
  expect(within(row).getByRole("link", { name: /^gh/ })).toHaveAttribute("href", "/clis/gh");
  expect(within(row).getByRole("link", { name: /^Check/ })).toHaveAttribute("href", "/clis/gh");

  // Once the command is current the daemon's list has no such item, and the row goes.
  state.attention = EMPTY_ATTENTION;
  await waitFor(() => expect(listener).not.toBeNull());
  act(() => {
    listener?.({
      type: "change",
      change: { seq: 2, kind: "attention", id: null, op: "upsert" },
    });
  });
  expect(await screen.findByText("Nothing needs you")).toBeInTheDocument();
  expect(within(needsYou()).queryByText("gh")).toBeNull();
});
