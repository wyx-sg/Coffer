// src/pages/activity/ActivityPage.test.tsx — the Activity page: four tabs, the filter row, the drawer, live insertion and holding, export, hand-offs.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import type { StreamMessage } from "@/lib/events/eventStream";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));

// The change feed: tests drive its listener by hand instead of opening a stream.
const stream: { listener: ((m: StreamMessage) => void) | null } = { listener: null };
vi.mock("@/lib/events/eventStream", () => ({
  followDaemonEvents: (onMessage: (m: StreamMessage) => void, signal: AbortSignal) => {
    stream.listener = onMessage;
    return new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve()));
  },
}));

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({
    data: [{ uid: "a-cc", type: "claude_code", display_name: "Claude Code", name: "claude_code" }],
  }),
}));

const saved: { name: string; type: string; content: string }[] = [];
vi.mock("@/lib/activity/export", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/activity/export")>();
  return {
    ...actual,
    saveFile: (name: string, type: string, content: string) => saved.push({ name, type, content }),
  };
});

const { getApiClient } = await import("@/lib/api/client");
const { ActivityPage } = await import("./ActivityPage");

const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

const AUDIT_ENTRY = {
  id: 42,
  timestamp: ago(30_000),
  event_type: "resource_created",
  resource_kind: "mcp_server",
  resource_name: "filesystem",
  actor: "api",
  details: { some_key: "some_value" },
};

const INVOCATION = {
  id: 7,
  timestamp: ago(20_000),
  resource_uid: "u-github",
  resource_name: "github",
  capability_type: "tool",
  capability_key: "search_issues",
  duration_ms: 42,
  status: "ok",
  error_message: null,
  session_id: "s-1",
  agent_uid: "a-cc",
  handoff: null,
};

const DAEMON_RECORD = {
  offset: 1000,
  handoff: null,
  timestamp: ago(10_000),
  level: "warning",
  event: "auto_sync_failed",
  record: {
    event: "auto_sync_failed",
    level: "warning",
    logger: "coffer.sync",
    error: "connection refused",
  },
};

interface Data {
  audit: unknown[];
  invocations: unknown[];
  daemon: unknown[];
  failing?: string;
  /** The audit log has an older page behind its first. */
  olderAudit?: boolean;
}

/**
 * Answer each route from `data` — mutable, so a test can add records and let
 * the next read find them. Totals are the rows each route holds.
 */
function mockApi(initial: Partial<Data> = {}) {
  const data: Data = { audit: [], invocations: [], daemon: [], ...initial };
  const fail = {
    data: undefined,
    error: { error: { code: "NOT_FOUND", message: "route not found" } },
  };
  const get = vi
    .fn()
    .mockImplementation((path: string, init?: { params?: { query?: Record<string, unknown> } }) => {
      const query = init?.params?.query ?? {};
      if (path === data.failing) return Promise.resolve(fail);
      // Each route searches the way the daemon does: the text, in any case, anywhere in the row.
      const matches = (row: unknown) =>
        (!query.q || JSON.stringify(row).toLowerCase().includes(String(query.q).toLowerCase())) &&
        (!query.since ||
          !(row as { timestamp?: string }).timestamp ||
          (row as { timestamp: string }).timestamp >= String(query.since));
      if (path === "/audit") {
        const limit = Number(query.limit ?? 50);
        const rows = data.audit.filter(matches);
        return Promise.resolve({
          data: {
            entries: rows.slice(0, limit),
            next_cursor: data.olderAudit && !query.cursor ? "older" : null,
            total: rows.length + (data.olderAudit ? 200 : 0),
          },
        });
      }
      if (path === "/mcp/invocations") {
        let rows = (data.invocations as (typeof INVOCATION)[]).filter(matches);
        if (query.status === "failed") rows = rows.filter((r) => r.status !== "ok");
        else if (query.status) rows = rows.filter((r) => r.status === query.status);
        const limit = Number(query.limit ?? 50);
        return Promise.resolve({
          data: { invocations: rows.slice(0, limit), next_cursor: null, total: rows.length },
        });
      }
      if (path === "/daemon/logs") {
        const records = data.daemon.filter(matches);
        return Promise.resolve({
          data: {
            records,
            next_cursor: null,
            total: query.with_total ? records.length : null,
            total_is_floor: false,
            path: "/Users/me/.coffer/logs/daemon.log",
          },
        });
      }
      if (path === "/retention/policies") {
        return Promise.resolve({
          data: {
            policies: [
              { table_name: "audit_log", retention_days: 365 },
              { table_name: "mcp_invocations", retention_days: 30 },
            ],
          },
        });
      }
      if (path === "/resources") {
        return Promise.resolve({
          data: {
            resources: [
              { uid: "u-github", name: "github", title: null, kind: "mcp_server" },
              { uid: "u-linear", name: "linear", title: null, kind: "mcp_server" },
            ],
          },
        });
      }
      return Promise.resolve({
        data: { status: "ready", version: "0.0.0", started_at: ago(0), port: 1 },
      });
    });
  vi.mocked(getApiClient).mockReturnValue({ GET: get } as unknown as ReturnType<
    typeof getApiClient
  >);
  return { get, data };
}

let qc: QueryClient;

function wrap(ui: React.ReactNode, initialEntries: string[] = ["/activity"]) {
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false as never } },
  });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

/** Re-read every log's newest page, as the poll does. */
async function pollHeads() {
  await act(async () => {
    await qc.refetchQueries({
      predicate: (q) => JSON.stringify(q.queryKey).includes('"view":"head"'),
    });
  });
}

const tab = (name: RegExp) => screen.getByRole("tab", { name });
// Radix activates a tab on mousedown, not on click.
const openTab = (name: RegExp) => fireEvent.mouseDown(tab(name));
const drawer = () => screen.findByRole("dialog");
/** The filter row's pill by its name ("By", "Kind: MCP calls"). */
const pill = (name: string) => screen.getByRole("button", { name: new RegExp(`^${name}`) });
const headers = () =>
  screen
    .getAllByRole("columnheader")
    .map((h) => h.textContent ?? "")
    .filter((h) => h !== "");
const search = (placeholder: string) => screen.getByLabelText(placeholder);
const list = () => document.querySelector("[data-activity-list]") as HTMLElement;
/** A call's `server.tool`, however the row splits it into spans. */
const target =
  (text: string) =>
  (_: string, el: Element | null): boolean =>
    el?.hasAttribute("data-call-target") === true && el.textContent === text;

beforeEach(() => {
  vi.clearAllMocks();
  saved.length = 0;
  stream.listener = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ActivityPage", () => {
  test("opens on Everything, merging the three records newest first", async () => {
    mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION], daemon: [DAEMON_RECORD] });
    render(wrap(<ActivityPage />));

    expect(screen.getByRole("heading", { name: /Activity/ })).toBeInTheDocument();
    expect(
      screen.getByText("Every change, tool call and daemon record, newest first."),
    ).toBeVisible();
    expect(tab(/everything/i)).toHaveAttribute("data-state", "active");
    await screen.findByText("Added filesystem");
    const rows = within(list())
      .getAllByRole("row")
      .filter((r) => r.hasAttribute("data-record"));
    expect(rows.map((r) => r.getAttribute("data-record")?.split(":")[0])).toEqual([
      "daemon",
      "call",
      "change",
    ]);
    expect(headers()).toEqual(["Time", "Event", "By", "Took"]);
    // The day is a heading row inside the box; no summary line sits above it.
    expect(screen.getByText(/^Today · /)).toBeInTheDocument();
    expect(screen.queryByText(/in the last hour/)).not.toBeInTheDocument();
  });

  test("tabs carry no counts, and the header says Live or Reconnecting", async () => {
    mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION], daemon: [DAEMON_RECORD] });
    render(wrap(<ActivityPage />));
    await screen.findByText("Added filesystem");
    expect(tab(/^Changes/)).toHaveTextContent(/^Changes$/);
    expect(tab(/^MCP calls/)).toHaveTextContent(/^MCP calls$/);
    expect(tab(/^Everything/)).toHaveTextContent(/^Everything$/);
    // The change feed is not open in a test: the dot says so in words.
    expect(screen.getByText("Reconnecting…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
  });

  test("the tab lives in the URL; the default needs no parameter", async () => {
    mockApi({ daemon: [DAEMON_RECORD] });
    let search = "";
    function Probe() {
      search = useLocation().search;
      return null;
    }
    render(
      wrap(
        <>
          <ActivityPage />
          <Probe />
        </>,
        ["/activity?tab=daemon"],
      ),
    );
    expect(tab(/daemon log/i)).toHaveAttribute("data-state", "active");
    openTab(/mcp calls/i);
    await waitFor(() => expect(search).toBe("?tab=mcp"));
    openTab(/everything/i);
    await waitFor(() => expect(search).toBe(""));
  });

  test("an old ?tab=changes link still opens Changes", () => {
    mockApi();
    render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
    expect(tab(/^Changes/)).toHaveAttribute("data-state", "active");
  });

  test("the free text narrows what is shown, and the URL keeps it", async () => {
    mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION] });
    let query = "";
    function Probe() {
      query = useLocation().search;
      return null;
    }
    render(
      wrap(
        <>
          <ActivityPage />
          <Probe />
        </>,
      ),
    );
    await screen.findByText("Added filesystem");
    fireEvent.change(search("Filter by name, tool or path"), {
      target: { value: "search_issues" },
    });
    await waitFor(() => expect(screen.queryByText("Added filesystem")).not.toBeInTheDocument());
    expect(await screen.findByText(target("github.search_issues"))).toBeInTheDocument();
    expect(query).toBe("?q=search_issues");
  });

  acceptance("web-ui", "a link opens already searching", async () => {
    mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION] });
    render(wrap(<ActivityPage />, ["/activity?tab=mcp&q=github"]));
    expect(search("Tool, server or session")).toHaveValue("github");
    await screen.findByText(target("github.search_issues"));
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(search("Tool, server or session")).toHaveValue(""));
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });

  test("the filter row reads search, time range, By, Kind — and has no Server pill", async () => {
    mockApi({ audit: [AUDIT_ENTRY] });
    render(wrap(<ActivityPage />));
    await screen.findByText("Added filesystem");
    expect(pill("Last hour")).toBeInTheDocument();
    expect(pill("By")).toBeInTheDocument();
    expect(pill("Kind")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Server/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Agent/ })).not.toBeInTheDocument();
    const order = [
      search("Filter by name, tool or path"),
      pill("Last hour"),
      pill("By"),
      pill("Kind"),
    ];
    for (let i = 1; i < order.length; i += 1) {
      expect(
        order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    }
  });

  test("the By pill groups agents and who else, with no counts, and filters the calls", async () => {
    const { get } = mockApi({ invocations: [INVOCATION] });
    render(wrap(<ActivityPage />));
    await screen.findByText(target("github.search_issues"));
    fireEvent.click(pill("By"));
    const options = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(options).toEqual(["Claude Code", "You", "CLI", "Coffer", "Sync"]);
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.getByText("Not an agent")).toBeInTheDocument();
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: "Claude Code" }));
    expect(pill("By")).toHaveTextContent(/By:\s*Claude Code$/);
    await waitFor(() =>
      expect(
        get.mock.calls.some(
          (c: unknown[]) =>
            c[0] === "/mcp/invocations" &&
            (c[1] as { params: { query: Record<string, unknown> } }).params.query.agent_uid ===
              "a-cc",
        ),
      ).toBe(true),
    );
  });

  test("on MCP calls the By pill lists agents only", async () => {
    mockApi({ invocations: [INVOCATION] });
    render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
    await screen.findByText(target("github.search_issues"));
    fireEvent.click(pill("By"));
    expect((await screen.findAllByRole("option")).map((o) => o.textContent)).toEqual([
      "Claude Code",
    ]);
  });

  acceptance("web-ui", "nothing recorded hides the filter row and Export", async () => {
    mockApi();
    render(wrap(<ActivityPage />));
    expect(await screen.findByText("Nothing has happened yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Changes you make in Coffer and the tools agents call through it show up here.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect an agent" })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(screen.getByRole("link", { name: "Add an MCP server" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Filter by name, tool or path")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export" })).not.toBeInTheDocument();
    expect(tab(/^Changes/)).toBeInTheDocument();
  });

  test("an empty hour is not a first run when older records exist", async () => {
    mockApi({ audit: [{ ...AUDIT_ENTRY, timestamp: ago(3 * 86_400_000) }] });
    render(wrap(<ActivityPage />));
    expect(await screen.findByText("Nothing in this time range")).toBeInTheDocument();
    expect(pill("Last hour")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
  });

  test("a change announced on the event stream re-reads the audit log's newest page", async () => {
    const { get } = mockApi({ audit: [AUDIT_ENTRY] });
    render(wrap(<ActivityPage />));
    await screen.findByText("Added filesystem");
    const before = get.mock.calls.filter((c: unknown[]) => c[0] === "/audit").length;
    act(() =>
      stream.listener?.({
        type: "change",
        change: { seq: 1, kind: "skill", id: "u", op: "upsert" },
      }),
    );
    await waitFor(() =>
      expect(get.mock.calls.filter((c: unknown[]) => c[0] === "/audit").length).toBeGreaterThan(
        before,
      ),
    );
  });
});

acceptance("web-ui", "activity gives each record its own tab", async () => {
  mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));

  openTab(/^Changes/);
  expect(await screen.findByText("Added filesystem")).toBeInTheDocument();
  expect(screen.queryByText("resource_created")).not.toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Change", "By"]);
  // Changes has its own Kind pill with the eleven kinds of change, flat.
  fireEvent.click(pill("Kind"));
  expect((await screen.findAllByRole("option")).map((o) => o.textContent)).toEqual([
    "MCP servers",
    "Skills",
    "Agents",
    "Model providers",
    "Channels",
    "Secrets",
    "Sync",
    "Settings",
    "Knowledge",
    "Memory",
    "CLIs",
  ]);
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

  openTab(/mcp calls/i);
  expect(await screen.findByText(target("github.search_issues"))).toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Agent", "Server · tool", "Took", "Status"]);
  expect(screen.queryByText("u-github")).not.toBeInTheDocument();
  expect(screen.getByText("42 ms")).toBeInTheDocument();
  expect(screen.queryByText("Added filesystem")).not.toBeInTheDocument();

  openTab(/daemon log/i);
  expect(await screen.findByText("auto_sync_failed")).toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Level", "Logger", "Message"]);
  expect(screen.getByText("warning")).toBeInTheDocument();
  expect(screen.getByText("coffer.sync")).toBeInTheDocument();
});

acceptance("web-ui", "activity row expands to its raw record", async () => {
  mockApi({ audit: [AUDIT_ENTRY], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));

  const line = await screen.findByText("Added filesystem");
  fireEvent.click(line.closest("tr")!);
  const panel = await drawer();
  // The raw JSON is folded until asked for.
  expect(panel.querySelector(".cm-content")).toBeNull();
  fireEvent.click(within(panel).getByRole("button", { name: "Raw log" }));
  await waitFor(() =>
    expect(panel.querySelector(".cm-content")?.textContent).toContain('"some_key": "some_value"'),
  );
  expect(panel.querySelector(".cm-content")?.textContent).toContain('"id": 42');

  fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  // A daemon record on Everything opens in the drawer too.
  fireEvent.click((await screen.findByText("auto_sync_failed")).closest("tr")!);
  const daemonPanel = await drawer();
  fireEvent.click(within(daemonPanel).getByRole("button", { name: "Raw log" }));
  await waitFor(() =>
    expect(daemonPanel.querySelector(".cm-content")?.textContent).toContain(
      '"error": "connection refused"',
    ),
  );
});

test("the drawer steps with the arrow keys and gives focus back to the row", async () => {
  mockApi({
    audit: [
      AUDIT_ENTRY,
      { ...AUDIT_ENTRY, id: 41, resource_name: "older", timestamp: ago(60_000) },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  const row = (await screen.findByText("Added filesystem")).closest("tr")!;
  row.focus();
  fireEvent.click(row);
  const panel = await drawer();
  expect(within(panel).getByRole("heading", { name: "Added filesystem" })).toBeInTheDocument();
  fireEvent.keyDown(panel, { key: "ArrowDown" });
  expect(await within(panel).findByRole("heading", { name: "Added older" })).toBeInTheDocument();
  fireEvent.keyDown(panel, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

acceptance("web-ui", "a daemon log row opens in place", async () => {
  mockApi({
    daemon: [
      {
        ...DAEMON_RECORD,
        level: "error",
        event: "upstream call failed server=github tool=search_issues",
        handoff: { prompt: "Please find out why the daemon logged this error" },
        record: {
          ...DAEMON_RECORD.record,
          level: "error",
          logger: "mcp.gateway",
          continuation: ["Traceback (most recent call last):", "httpx.ConnectError: refused"],
        },
      },
      {
        ...DAEMON_RECORD,
        offset: 2000,
        level: "error",
        event: "KeyError: 'uid'",
        record: { level: "error", logger: "coffer.overview", event: "KeyError: 'uid'" },
      },
    ],
    invocations: [INVOCATION],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=daemon"]));
  const row = (await screen.findByText(/upstream call failed/)).closest("tr")!;
  fireEvent.click(row);
  expect(row).toHaveAttribute("aria-expanded", "true");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByText(/httpx\.ConnectError: refused/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy record" })).toBeInTheDocument();
  // An error about the environment leads its button row with the hand-off.
  const buttons = within(row.nextElementSibling as HTMLElement).getAllByRole("button");
  expect(buttons[0]).toHaveAccessibleName(/Ask an agent|Copy prompt/);

  // A Coffer-internal error offers only Copy record.
  fireEvent.click(screen.getByText("KeyError: 'uid'").closest("tr")!);
  expect(screen.getAllByRole("button", { name: "Copy record" })).toHaveLength(1);
  expect(
    screen.queryByRole("button", { name: /Ask an agent|Copy prompt/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(row);

  // "Show the MCP call" lands on the MCP calls tab, looking for that call.
  fireEvent.click(screen.getByRole("button", { name: "Show the MCP call" }));
  await waitFor(() => expect(tab(/mcp calls/i)).toHaveAttribute("data-state", "active"));
  expect(search("Tool, server or session")).toHaveValue("github.search_issues");
  expect(await screen.findByText(target("github.search_issues"))).toBeInTheDocument();
});

test("a failed call opens with its error first", async () => {
  mockApi({
    invocations: [{ ...INVOCATION, status: "error", error_message: "Connection refused" }],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  fireEvent.click((await screen.findByText(target("github.search_issues"))).closest("tr")!);
  const panel = await drawer();
  expect(within(panel).getByRole("alert")).toHaveTextContent("Couldn't reach github");
  expect(within(panel).getByRole("alert")).toHaveTextContent("Connection refused");
  expect(within(panel).getByRole("link", { name: "Open github" })).toHaveAttribute(
    "href",
    "/mcp-servers/github",
  );
});

acceptance("web-ui", "an unanswered call and an environment error carry the hand-off", async () => {
  mockApi({
    invocations: [
      {
        ...INVOCATION,
        status: "error",
        error_message: "Connection refused",
        handoff: { prompt: "Please find out why a call to github could not reach it" },
      },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  fireEvent.click((await screen.findByText(target("github.search_issues"))).closest("tr")!);
  const card = within(await drawer()).getByRole("alert");
  expect(within(card).getAllByRole("button")[0]).toHaveAccessibleName(/Ask an agent|Copy prompt/);
  // The drawer's footer is the server's page; the old "Daemon log records" step is gone.
  expect(screen.queryByRole("button", { name: "Daemon log records" })).not.toBeInTheDocument();
});

test("a denied call and an upstream's own error get no hand-off", async () => {
  mockApi({
    invocations: [
      { ...INVOCATION, id: 8, status: "denied", error_message: null },
      {
        ...INVOCATION,
        id: 9,
        status: "error",
        error_message: "upstream tool returned an error result (isError)",
      },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  const rows = await screen.findAllByText(target("github.search_issues"));
  for (const r of rows) {
    fireEvent.click(r.closest("tr")!);
    const card = within(await drawer()).getByRole("alert");
    expect(within(card).queryByRole("button")).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  }
});

acceptance("resource-framework", "the Activity drawer shows a record's trace id", async () => {
  mockApi({
    audit: [{ ...AUDIT_ENTRY, trace_id: "req-a1b2" }],
    invocations: [{ ...INVOCATION, trace_id: "mcp-c3d4" }],
  });
  const { unmount } = render(wrap(<ActivityPage />));
  fireEvent.click((await screen.findByText(/filesystem/)).closest("tr")!);
  const change = await drawer();
  expect(within(change).getByText("Trace id")).toBeInTheDocument();
  expect(within(change).getByText("req-a1b2")).toBeInTheDocument();
  unmount();

  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  fireEvent.click((await screen.findByText(target("github.search_issues"))).closest("tr")!);
  const call = await drawer();
  expect(within(call).getByText("mcp-c3d4")).toBeInTheDocument();
});

test("a record written with no trace id shows no trace row", async () => {
  mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />));
  fireEvent.click((await screen.findByText(/filesystem/)).closest("tr")!);
  expect(within(await drawer()).queryByText("Trace id")).not.toBeInTheDocument();
});

test("a change's before and after read as a diff, with Copy details and Open in the footer", async () => {
  mockApi({
    audit: [
      {
        ...AUDIT_ENTRY,
        event_type: "resource_updated",
        details: { before: { url: "https://old" }, after: { url: "https://new" } },
      },
    ],
  });
  render(wrap(<ActivityPage />));
  fireEvent.click((await screen.findByText(/filesystem/)).closest("tr")!);
  const panel = await drawer();
  expect(panel.querySelector('[data-line="remove"]')?.textContent).toContain("https://old");
  expect(panel.querySelector('[data-line="add"]')?.textContent).toContain("https://new");
  expect(within(panel).getByText("Secret values are never recorded.")).toBeInTheDocument();
  expect(within(panel).getByRole("button", { name: "Copy details" })).toBeInTheDocument();
  expect(within(panel).getByRole("link", { name: "Open filesystem" })).toBeInTheDocument();
});

acceptance("web-ui", "a failing record shows its error inside its own tab", async () => {
  mockApi({ audit: [AUDIT_ENTRY], daemon: [DAEMON_RECORD], failing: "/mcp/invocations" });
  render(wrap(<ActivityPage />));

  // Everything says which record is missing and still shows the other two.
  expect(await screen.findByText("MCP calls couldn't be loaded")).toBeInTheDocument();
  expect(await screen.findByText("Added filesystem")).toBeInTheDocument();
  expect(screen.getByText("auto_sync_failed")).toBeInTheDocument();
  // The failed record's tab carries a warning icon.
  expect(
    within(tab(/^MCP calls/)).getByRole("img", { name: "Couldn't be loaded" }),
  ).toBeInTheDocument();
  expect(within(tab(/^Changes/)).queryByRole("img")).not.toBeInTheDocument();

  openTab(/mcp calls/i);
  expect(await screen.findByText("Not found.")).toBeInTheDocument();

  openTab(/^Changes/);
  expect(await screen.findByText("Added filesystem")).toBeInTheDocument();
  expect(screen.queryByText("Not found.")).not.toBeInTheDocument();
});

acceptance("web-ui", "a failed log is one banner that retries only that log", async () => {
  const { get } = mockApi({
    audit: [AUDIT_ENTRY],
    daemon: [DAEMON_RECORD],
    failing: "/mcp/invocations",
  });
  render(wrap(<ActivityPage />));
  const note = await screen.findByRole("status");
  expect(note).toHaveTextContent("MCP calls couldn't be loaded");
  expect(note).toHaveTextContent("Changes and daemon records below are complete.");
  expect(within(note).queryByRole("button", { name: /close|dismiss|ignore/i })).toBeNull();
  const reads = (path: string) => get.mock.calls.filter((c: unknown[]) => c[0] === path).length;
  const audit = reads("/audit");
  const calls = reads("/mcp/invocations");
  fireEvent.click(within(note).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(reads("/mcp/invocations")).toBeGreaterThan(calls));
  expect(reads("/audit")).toBe(audit);
  expect(screen.queryByText("Changes and daemon records")).not.toBeInTheDocument();
});

acceptance("web-ui", "each activity tab reads its owner's route", async () => {
  const { get } = mockApi({
    audit: [AUDIT_ENTRY],
    invocations: [INVOCATION],
    daemon: [DAEMON_RECORD],
  });
  // The three owners' routes, plus the agent list the By pill offers and the
  // attention list every page header reads for the items ignored on it.
  // Anything else would be a route of the Activity page's own.
  const ALLOWED = new Set([
    "/audit",
    "/mcp/invocations",
    "/daemon/logs",
    "/resources",
    "/attention",
    "/retention/policies",
  ]);
  const requested = () => get.mock.calls.map((c: unknown[]) => c[0] as string);

  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  expect(await screen.findByText("Added filesystem")).toBeInTheDocument();
  expect(requested()).toContain("/audit");
  // The tab shows the audit log's rows and nothing else.
  expect(screen.queryByText(target("github.search_issues"))).not.toBeInTheDocument();

  openTab(/mcp calls/i);
  expect(await screen.findByText(target("github.search_issues"))).toBeInTheDocument();
  expect(screen.queryByText("Added filesystem")).not.toBeInTheDocument();

  openTab(/daemon log/i);
  expect(await screen.findByText("auto_sync_failed")).toBeInTheDocument();
  expect(screen.queryByText(target("github.search_issues"))).not.toBeInTheDocument();

  expect(new Set(requested()).size).toBeGreaterThan(0);
  expect(requested().every((p) => ALLOWED.has(p))).toBe(true);
});

acceptance("web-ui", "new records stream in at the top", async () => {
  const { data } = mockApi({ invocations: [INVOCATION] });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  await screen.findByText(target("github.search_issues"));

  data.invocations = [
    { ...INVOCATION, id: 9, timestamp: ago(1_000), capability_key: "create_issue" },
    { ...INVOCATION, id: 8, timestamp: ago(2_000), capability_key: "list_issues" },
    INVOCATION,
  ];
  await pollHeads();

  await waitFor(() => expect(screen.getByText(target("github.create_issue"))).toBeInTheDocument());
  const rows = within(list())
    .getAllByRole("row")
    .filter((r) => r.hasAttribute("data-record"));
  expect(rows[0]).toHaveTextContent("github.create_issue");
  expect(rows[1]).toHaveTextContent("github.list_issues");
  expect(screen.queryByRole("button", { name: /pause|resume/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /new$/ })).not.toBeInTheDocument();
});

acceptance("web-ui", "new records are held while the user reads", async () => {
  const { data } = mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  await screen.findByText("Added filesystem");

  // Scrolled down: nothing moves.
  list().scrollTop = 200;
  fireEvent.scroll(list());
  data.audit = [
    { ...AUDIT_ENTRY, id: 45, timestamp: ago(1_000), resource_name: "three" },
    { ...AUDIT_ENTRY, id: 44, timestamp: ago(2_000), resource_name: "two" },
    { ...AUDIT_ENTRY, id: 43, timestamp: ago(3_000), resource_name: "one" },
    AUDIT_ENTRY,
  ];
  await pollHeads();

  const pillButton = await screen.findByRole("button", { name: "3 new" });
  expect(screen.queryByText("Added three")).not.toBeInTheDocument();
  const rows = () =>
    within(list())
      .getAllByRole("row")
      .filter((r) => r.hasAttribute("data-record"));
  expect(rows()).toHaveLength(1);

  fireEvent.click(pillButton);
  await waitFor(() => expect(rows()).toHaveLength(4));
  expect(rows()[0]).toHaveTextContent("Added three");
  expect(screen.queryByRole("button", { name: /new$/ })).not.toBeInTheDocument();
});

test("an open record holds new ones too", async () => {
  const { data } = mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  fireEvent.click((await screen.findByText("Added filesystem")).closest("tr")!);
  await drawer();
  data.audit = [
    { ...AUDIT_ENTRY, id: 50, timestamp: ago(1_000), resource_name: "later" },
    AUDIT_ENTRY,
  ];
  await pollHeads();
  // The drawer's scrim covers the page, so the pill is in the document but not reachable by role.
  expect(await screen.findByRole("button", { name: "1 new", hidden: true })).toBeInTheDocument();
  expect(screen.queryByText("Added later")).not.toBeInTheDocument();
});

test("a new record the filters exclude is neither inserted nor counted", async () => {
  const { data, get } = mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  await screen.findByText("Added filesystem");
  fireEvent.change(search("Filter changes"), { target: { value: "filesystem" } });
  // The text reaches the route once typing pauses.
  await waitFor(() =>
    expect(
      get.mock.calls.some(
        (c: unknown[]) =>
          c[0] === "/audit" &&
          (c[1] as { params: { query: Record<string, unknown> } }).params.query.q === "filesystem",
      ),
    ).toBe(true),
  );
  await screen.findByText("Added filesystem");
  list().scrollTop = 200;
  fireEvent.scroll(list());
  data.audit = [
    { ...AUDIT_ENTRY, id: 60, timestamp: ago(1_000), resource_name: "other" },
    AUDIT_ENTRY,
  ];
  await pollHeads();
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("button", { name: /new$/ })).not.toBeInTheDocument();
});

acceptance("web-ui", "export from the menu honours the filters", async () => {
  const { get } = mockApi({
    invocations: [
      { ...INVOCATION, id: 1, status: "error", error_message: "boom" },
      { ...INVOCATION, id: 2, status: "ok" },
      { ...INVOCATION, id: 3, status: "ok", resource_uid: "u-linear", resource_name: "linear" },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp&q=github"]));
  await waitFor(() => expect(screen.getAllByText(target("github.search_issues")).length).toBe(2));

  // Status is the first control of the row: All / OK / Failed.
  const group = screen.getByRole("group", { name: "Call status" });
  expect(
    within(group)
      .getAllByRole("button")
      .map((b) => b.textContent),
  ).toEqual(["All", "OK", "Failed"]);
  fireEvent.click(within(group).getByRole("button", { name: "Failed" }));
  await waitFor(() => expect(screen.getAllByText(target("github.search_issues"))).toHaveLength(1));

  // Export is a visible ghost button with a JSON / CSV menu — not a ⋯ menu.
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "CSV" }));
  await waitFor(() => expect(saved).toHaveLength(1));
  const lines = saved[0].content.trim().split("\r\n");
  expect(lines).toHaveLength(2);
  expect(lines[1]).toContain("github");
  expect(lines[1]).toContain("error");
  const exportRead = get.mock.calls.filter(
    (c: unknown[]) =>
      c[0] === "/mcp/invocations" &&
      (c[1] as { params: { query: Record<string, unknown> } }).params.query.limit === 500,
  );
  expect(exportRead.at(-1)?.[1]).toMatchObject({
    params: { query: { q: "github", status: "failed" } },
  });

  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "JSON" }));
  await waitFor(() => expect(saved).toHaveLength(2));
  const json = JSON.parse(saved[1].content) as { id: number }[];
  expect(json.map((r) => r.id)).toEqual([1]);
});

test("Failed means error, timeout and denied", async () => {
  mockApi({
    invocations: [
      INVOCATION,
      { ...INVOCATION, id: 8, status: "error" },
      { ...INVOCATION, id: 9, status: "timeout" },
      { ...INVOCATION, id: 10, status: "denied" },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp&status=failed"]));
  await waitFor(() => expect(screen.getAllByText(target("github.search_issues"))).toHaveLength(3));
  expect(screen.getAllByText(/^(Error|Timeout|Denied)$/).map((e) => e.textContent)).toEqual(
    ["Error", "Timeout", "Denied"].sort((a, b) => 0 * a.length * b.length),
  );
  expect(screen.queryByText(/calls · /)).not.toBeInTheDocument();
});

test("MCP calls sorts by Took, right-aligned, with the day heading gone while sorted", async () => {
  mockApi({
    invocations: [
      { ...INVOCATION, id: 8, duration_ms: 5 },
      { ...INVOCATION, id: 9, duration_ms: 900 },
      { ...INVOCATION, id: 10, duration_ms: 50 },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  await screen.findAllByText(target("github.search_issues"));
  const times = () =>
    within(list())
      .getAllByRole("row")
      .filter((r) => r.hasAttribute("data-record"))
      .map((r) => r.querySelector("td:nth-child(4)")?.textContent);
  expect(times()).toEqual(["5 ms", "900 ms", "50 ms"]);
  fireEvent.click(screen.getByRole("button", { name: "Took" }));
  expect(times()).toEqual(["900 ms", "50 ms", "5 ms"]);
  fireEvent.click(screen.getByRole("button", { name: "Took" }));
  expect(times()).toEqual(["5 ms", "50 ms", "900 ms"]);
  fireEvent.click(screen.getByRole("button", { name: "Took" }));
  expect(times()).toEqual(["5 ms", "900 ms", "50 ms"]);
});

test("the Kind pill on Everything has three flat values and no counts", async () => {
  mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));
  await screen.findByText("auto_sync_failed");

  fireEvent.click(pill("Kind"));
  expect((await screen.findAllByRole("option")).map((o) => o.textContent)).toEqual([
    "MCP calls",
    "Changes",
    "Daemon records",
  ]);
  fireEvent.click(screen.getByRole("option", { name: "MCP calls" }));
  fireEvent.click(screen.getByRole("option", { name: "Changes" }));
  expect(pill("Kind")).toHaveTextContent(/Kind:\s*MCP calls, Changes/);
  await waitFor(() => expect(screen.queryByText("auto_sync_failed")).not.toBeInTheDocument());
  expect(screen.getByText("Added filesystem")).toBeInTheDocument();
  expect(screen.getByText(target("github.search_issues"))).toBeInTheDocument();
});

test("the time range offers its windows and a custom range, and the URL keeps the choice", async () => {
  mockApi({ audit: [AUDIT_ENTRY] });
  let query = "";
  function Probe() {
    query = useLocation().search;
    return null;
  }
  render(
    wrap(
      <>
        <ActivityPage />
        <Probe />
      </>,
    ),
  );
  await screen.findByText("Added filesystem");
  fireEvent.click(pill("Last hour"));
  const options = await screen.findAllByRole("option");
  expect(options.map((o) => o.textContent)).toEqual([
    "Last hour",
    "Last 24 h",
    "Last 7 days",
    "Last 30 days",
    "Custom range…",
  ]);
  fireEvent.click(screen.getByRole("option", { name: "Last 7 days" }));
  expect(await screen.findByRole("button", { name: /Last 7 days/ })).toBeInTheDocument();
  expect(query).toBe("?range=7d");
});

test("the daemon log opens on the last 24 h and names its file with a link to Finder", async () => {
  mockApi({ daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />, ["/activity?tab=daemon"]));
  expect(await screen.findByRole("button", { name: /Last 24 h/ })).toBeInTheDocument();
  expect(await screen.findByText("~/.coffer/logs/daemon.log")).toBeInTheDocument();
  expect(screen.getByText("newest first")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open in Finder" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Open log file" })).not.toBeInTheDocument();
  // Level first, then search, time, Logger.
  const group = screen.getByRole("group", { name: "Log level" });
  expect(
    within(group)
      .getAllByRole("button")
      .map((b) => b.textContent),
  ).toEqual(["All", "Info", "Warnings", "Errors"]);
  expect(pill("Logger")).toBeInTheDocument();
});

acceptance("web-ui", "the box ends with what is shown and what is kept", async () => {
  mockApi({ audit: [AUDIT_ENTRY], olderAudit: true });
  const { unmount } = render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  expect(await screen.findByRole("button", { name: "Load 50 more" })).toBeInTheDocument();
  expect(screen.getByText(/Showing 1 of 201 · next 50 from before \d\d:\d\d/)).toBeInTheDocument();
  expect(screen.queryByText(/MCP calls are kept/)).not.toBeInTheDocument();
  unmount();
  mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  expect(await screen.findByText(/That's everything kept\./)).toBeInTheDocument();
  expect(await screen.findByText(/MCP calls are kept 30 days/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Settings › Data" })).toHaveAttribute(
    "href",
    "/settings/data",
  );
});

test("a failed call says how its server has been doing", async () => {
  mockApi({
    invocations: [{ ...INVOCATION, status: "error", error_message: "Connection refused" }],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  fireEvent.click((await screen.findByText(target("github.search_issues"))).closest("tr")!);
  const panel = await drawer();
  await waitFor(() =>
    expect(within(panel).getByRole("alert")).toHaveTextContent(
      /github has been failing since \d\d:\d\d — 1 error in the last 24 hours\./,
    ),
  );
});

test("a change of a kind this page has no words for still reads as a change", async () => {
  mockApi({
    audit: [
      {
        ...AUDIT_ENTRY,
        event_type: "provider_failed_over",
        resource_kind: "provider",
        resource_name: "anthropic-api",
        actor: "system",
        details: { before: { active: "gateway" }, after: { active: "anthropic-api" } },
      },
    ],
  });
  render(wrap(<ActivityPage />));
  fireEvent.click((await screen.findByText("provider_failed_over")).closest("tr")!);
  const panel = await drawer();
  expect(within(panel).getByText("Coffer")).toBeInTheDocument();
  expect(panel.querySelector('[data-line="add"]')?.textContent).toContain("anthropic-api");
});

acceptance("web-ui", "who and kind choose several values", async () => {
  mockApi({
    audit: [
      { ...AUDIT_ENTRY, id: 43, actor: "ui", resource_name: "linear" },
      { ...AUDIT_ENTRY, id: 44, actor: "cli", resource_name: "jira" },
    ],
    invocations: [INVOCATION],
    daemon: [DAEMON_RECORD],
  });
  render(wrap(<ActivityPage />));
  await screen.findByText("auto_sync_failed");

  fireEvent.click(pill("By"));
  fireEvent.click(await screen.findByRole("option", { name: "Claude Code" }));
  fireEvent.click(screen.getByRole("option", { name: "You" }));
  expect(pill("By")).toHaveTextContent(/By:\s*Claude Code, You/);
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());

  await waitFor(() => expect(screen.queryByText("Added jira")).not.toBeInTheDocument());
  expect(screen.getByText("Added linear")).toBeInTheDocument();
  expect(screen.getByText(target("github.search_issues"))).toBeInTheDocument();
  expect(screen.queryByText("auto_sync_failed")).not.toBeInTheDocument();
});
