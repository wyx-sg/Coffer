// src/pages/activity/ActivityPage.test.tsx — the Activity page: four tabs with counts, filters, the drawer, live insertion and holding, export.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import type { StreamMessage } from "@/lib/events/eventStream";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));

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
};

const DAEMON_RECORD = {
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
      if (path === "/audit") {
        const limit = Number(query.limit ?? 50);
        return Promise.resolve({
          data: {
            entries: data.audit.slice(0, limit),
            next_cursor: data.olderAudit && !query.cursor ? "older" : null,
            total: data.audit.length + (data.olderAudit ? 200 : 0),
          },
        });
      }
      if (path === "/mcp/invocations") {
        let rows = data.invocations as (typeof INVOCATION)[];
        if (query.uid) rows = rows.filter((r) => r.resource_uid === query.uid);
        if (query.status) rows = rows.filter((r) => r.status === query.status);
        const limit = Number(query.limit ?? 50);
        return Promise.resolve({
          data: { invocations: rows.slice(0, limit), next_cursor: null, total: rows.length },
        });
      }
      if (path === "/daemon/logs") {
        return Promise.resolve({
          data: { records: data.daemon, path: "/Users/me/.coffer/logs/daemon.log" },
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
const headers = () =>
  screen
    .getAllByRole("columnheader")
    .map((h) => h.textContent ?? "")
    .filter((h) => h !== "");
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
    expect(tab(/everything/i)).toHaveAttribute("data-state", "active");
    await screen.findByText("Registered filesystem");
    const rows = within(list())
      .getAllByRole("row")
      .filter((r) => r.hasAttribute("data-record"));
    expect(rows.map((r) => r.getAttribute("data-record")?.split(":")[0])).toEqual([
      "daemon",
      "call",
      "change",
    ]);
    expect(headers()).toEqual(["Time", "Event", "By", "Took"]);
  });

  test("each tab carries its count", async () => {
    mockApi({
      audit: [AUDIT_ENTRY],
      invocations: [INVOCATION, { ...INVOCATION, id: 8 }],
      daemon: [DAEMON_RECORD],
    });
    render(wrap(<ActivityPage />));
    await waitFor(() => expect(tab(/^Changes/)).toHaveTextContent("Changes1"));
    expect(tab(/^MCP calls/)).toHaveTextContent("MCP calls2");
    expect(tab(/^Daemon log/)).toHaveTextContent("Daemon log1");
    expect(tab(/^Everything/)).toHaveTextContent("Everything4");
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

  test("the free text narrows what is shown", async () => {
    mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION] });
    render(wrap(<ActivityPage />));
    await screen.findByText("Registered filesystem");
    fireEvent.change(screen.getByLabelText("Filter records"), {
      target: { value: "search_issues" },
    });
    await waitFor(() =>
      expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument(),
    );
    expect(screen.getByText(target("github.search_issues"))).toBeInTheDocument();
  });

  test("the agent filter narrows the calls to that agent's", async () => {
    const { get } = mockApi({ invocations: [INVOCATION] });
    render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
    await screen.findByText(target("github.search_issues"));
    fireEvent.click(screen.getByRole("button", { name: /^Agent:/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Claude Code" }));
    expect(screen.getByRole("button", { name: /^Agent:/ })).toHaveTextContent("Claude Code");
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

  test("nothing yet says what to do next", async () => {
    mockApi();
    render(wrap(<ActivityPage />));
    expect(await screen.findByText("Nothing has happened yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect an agent" })).toHaveAttribute(
      "href",
      "/agents",
    );
  });

  test("a change announced on the event stream re-reads the audit log's newest page", async () => {
    const { get } = mockApi({ audit: [AUDIT_ENTRY] });
    render(wrap(<ActivityPage />));
    await screen.findByText("Registered filesystem");
    const before = get.mock.calls.filter((c: unknown[]) => c[0] === "/audit").length;
    act(() =>
      stream.listener?.({
        type: "change",
        change: { seq: 1, kind: "skill", id: "u", rev: 2, op: "upsert" },
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
  expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
  expect(screen.queryByText("resource_created")).not.toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Event", "By"]);

  openTab(/mcp calls/i);
  expect(await screen.findByText(target("github.search_issues"))).toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Agent", "Server · tool", "Took", "Status"]);
  expect(screen.queryByText("u-github")).not.toBeInTheDocument();
  expect(screen.getByText("42 ms")).toBeInTheDocument();
  expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument();

  openTab(/daemon log/i);
  expect(await screen.findByText("auto_sync_failed")).toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Level", "Logger", "Message"]);
  expect(screen.getByText("warning")).toBeInTheDocument();
  expect(screen.getByText("coffer.sync")).toBeInTheDocument();
});

acceptance("web-ui", "activity row expands to its raw record", async () => {
  mockApi({ audit: [AUDIT_ENTRY], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));

  const line = await screen.findByText("Registered filesystem");
  fireEvent.click(line.closest("tr")!);
  const drawer = await screen.findByRole("complementary", { name: "Details" });
  await waitFor(() =>
    expect(drawer.querySelector(".cm-content")?.textContent).toContain('"some_key": "some_value"'),
  );
  expect(drawer.querySelector(".cm-content")?.textContent).toContain('"id": 42');

  fireEvent.click(within(drawer).getByRole("button", { name: "Close details" }));
  await waitFor(() =>
    expect(screen.queryByRole("complementary", { name: "Details" })).not.toBeInTheDocument(),
  );

  // A daemon record on Everything opens in the drawer too.
  fireEvent.click((await screen.findByText("auto_sync_failed")).closest("tr")!);
  const daemonDrawer = await screen.findByRole("complementary", { name: "Details" });
  await waitFor(() =>
    expect(daemonDrawer.querySelector(".cm-content")?.textContent).toContain(
      '"error": "connection refused"',
    ),
  );
});

acceptance("web-ui", "a daemon log row opens in place", async () => {
  mockApi({
    daemon: [
      {
        ...DAEMON_RECORD,
        level: "error",
        event: "upstream call failed server=github tool=search_issues",
        record: {
          ...DAEMON_RECORD.record,
          level: "error",
          logger: "mcp.gateway",
          continuation: ["Traceback (most recent call last):", "httpx.ConnectError: refused"],
        },
      },
    ],
    invocations: [INVOCATION],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=daemon"]));
  const row = (await screen.findByText(/upstream call failed/)).closest("tr")!;
  fireEvent.click(row);
  expect(row).toHaveAttribute("aria-expanded", "true");
  expect(screen.queryByRole("complementary", { name: "Details" })).not.toBeInTheDocument();
  expect(screen.getByText(/httpx\.ConnectError: refused/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy record" })).toBeInTheDocument();

  // "Show the MCP call" lands on the MCP calls tab, looking for that call.
  fireEvent.click(screen.getByRole("button", { name: "Show the MCP call" }));
  await waitFor(() => expect(tab(/mcp calls/i)).toHaveAttribute("data-state", "active"));
  expect(screen.getByLabelText("Filter records")).toHaveValue("github.search_issues");
  expect(await screen.findByText(target("github.search_issues"))).toBeInTheDocument();
});

test("a failed call opens with its error first", async () => {
  mockApi({
    invocations: [{ ...INVOCATION, status: "error", error_message: "Connection refused" }],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  fireEvent.click((await screen.findByText(target("github.search_issues"))).closest("tr")!);
  const drawer = await screen.findByRole("complementary", { name: "Details" });
  expect(within(drawer).getByRole("alert")).toHaveTextContent("Couldn't reach github");
  expect(within(drawer).getByRole("alert")).toHaveTextContent("Connection refused");
  expect(within(drawer).getByRole("link", { name: "Open github" })).toHaveAttribute(
    "href",
    "/mcp-servers/github",
  );
});

acceptance(
  "resource-framework",
  "the Activity drawer shows a record's trace id",
  async () => {
    mockApi({
      audit: [{ ...AUDIT_ENTRY, trace_id: "req-a1b2" }],
      invocations: [{ ...INVOCATION, trace_id: "mcp-c3d4" }],
    });
    const { unmount } = render(wrap(<ActivityPage />));
    fireEvent.click((await screen.findByText(/filesystem/)).closest("tr")!);
    const change = await screen.findByRole("complementary", { name: "Details" });
    expect(within(change).getByText("Trace id")).toBeInTheDocument();
    expect(within(change).getByText("req-a1b2")).toBeInTheDocument();
    unmount();

    render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
    fireEvent.click((await screen.findByText(target("github.search_issues"))).closest("tr")!);
    const call = await screen.findByRole("complementary", { name: "Details" });
    expect(within(call).getByText("mcp-c3d4")).toBeInTheDocument();
  },
);

test("a record written with no trace id shows no trace row", async () => {
  mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />));
  fireEvent.click((await screen.findByText(/filesystem/)).closest("tr")!);
  const drawer = await screen.findByRole("complementary", { name: "Details" });
  expect(within(drawer).queryByText("Trace id")).not.toBeInTheDocument();
});

test("a change's before and after read as a diff", async () => {
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
  const drawer = await screen.findByRole("complementary", { name: "Details" });
  expect(drawer.querySelector('[data-line="remove"]')?.textContent).toContain("https://old");
  expect(drawer.querySelector('[data-line="add"]')?.textContent).toContain("https://new");
});

acceptance("web-ui", "a failing record shows its error inside its own tab", async () => {
  mockApi({ audit: [AUDIT_ENTRY], daemon: [DAEMON_RECORD], failing: "/mcp/invocations" });
  render(wrap(<ActivityPage />));

  // Everything says which record is missing and still shows the other two.
  expect(await screen.findByText("MCP calls couldn't be loaded")).toBeInTheDocument();
  expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
  expect(screen.getByText("auto_sync_failed")).toBeInTheDocument();

  openTab(/mcp calls/i);
  expect(await screen.findByText("Not found.")).toBeInTheDocument();

  openTab(/^Changes/);
  expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
  expect(screen.queryByText("Not found.")).not.toBeInTheDocument();
});

acceptance("web-ui", "each activity tab reads its owner's route", async () => {
  const { get } = mockApi({
    audit: [AUDIT_ENTRY],
    invocations: [INVOCATION],
    daemon: [DAEMON_RECORD],
  });
  // The three owners' routes, plus the MCP server list the server filter
  // offers (the resource framework's). Anything else would be a route of the
  // Activity page's own.
  const ALLOWED = new Set(["/audit", "/mcp/invocations", "/daemon/logs", "/resources"]);
  const requested = () => get.mock.calls.map((c: unknown[]) => c[0] as string);

  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
  expect(requested()).toContain("/audit");
  // The tab shows the audit log's rows and nothing else.
  expect(screen.queryByText(target("github.search_issues"))).not.toBeInTheDocument();

  openTab(/mcp calls/i);
  expect(await screen.findByText(target("github.search_issues"))).toBeInTheDocument();
  expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument();

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
  await screen.findByText("Registered filesystem");

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

  const pill = await screen.findByRole("button", { name: "3 new" });
  expect(screen.queryByText("Registered three")).not.toBeInTheDocument();
  const rows = () =>
    within(list())
      .getAllByRole("row")
      .filter((r) => r.hasAttribute("data-record"));
  expect(rows()).toHaveLength(1);

  fireEvent.click(pill);
  await waitFor(() => expect(rows()).toHaveLength(4));
  expect(rows()[0]).toHaveTextContent("Registered three");
  expect(screen.queryByRole("button", { name: /new$/ })).not.toBeInTheDocument();
});

test("an open record holds new ones too", async () => {
  const { data } = mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  fireEvent.click((await screen.findByText("Registered filesystem")).closest("tr")!);
  await screen.findByRole("complementary", { name: "Details" });
  data.audit = [
    { ...AUDIT_ENTRY, id: 50, timestamp: ago(1_000), resource_name: "later" },
    AUDIT_ENTRY,
  ];
  await pollHeads();
  expect(await screen.findByRole("button", { name: "1 new" })).toBeInTheDocument();
  expect(screen.queryByText("Registered later")).not.toBeInTheDocument();
});

test("a new record the filters exclude is neither inserted nor counted", async () => {
  const { data } = mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  await screen.findByText("Registered filesystem");
  fireEvent.change(screen.getByLabelText("Filter records"), { target: { value: "filesystem" } });
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
      { ...INVOCATION, id: 3, status: "error", resource_uid: "u-linear", resource_name: "linear" },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  await waitFor(() => expect(screen.getAllByText(target("github.search_issues")).length).toBe(2));

  fireEvent.click(screen.getByRole("button", { name: /^Server:/ }));
  fireEvent.click(await screen.findByRole("option", { name: "github" }));
  // Let the first popover finish closing (it hands focus back to its pill).
  await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getAllByText(target("github.search_issues"))).toHaveLength(2));
  fireEvent.click(screen.getByRole("button", { name: /^Status:/ }));
  fireEvent.click(await screen.findByRole("option", { name: "Error" }));
  await waitFor(() => expect(screen.getAllByText(target("github.search_issues"))).toHaveLength(1));

  // No export button in the header: it lives in the ⋯ menu.
  expect(screen.queryByRole("button", { name: /export/i })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "More" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Export as CSV" }));
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
    params: { query: { uid: "u-github", status: "error" } },
  });

  fireEvent.click(screen.getByRole("button", { name: "More" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Export as JSON" }));
  await waitFor(() => expect(saved).toHaveLength(2));
  const json = JSON.parse(saved[1].content) as { id: number }[];
  expect(json.map((r) => r.id)).toEqual([1]);
});

test("the kind filter chooses several kinds, and the tabs keep their counts", async () => {
  mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));
  await screen.findByText("auto_sync_failed");
  await waitFor(() => expect(tab(/^Everything/)).toHaveTextContent("Everything3"));

  fireEvent.click(screen.getByRole("button", { name: /^Kind:/ }));
  fireEvent.click(await screen.findByRole("checkbox", { name: "MCP calls" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Changes" }));
  // Every change kind sits under Changes, ticked with it.
  expect(screen.getByRole("checkbox", { name: "MCP servers" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  expect(screen.getByText("Everything except daemon records")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Kind:/ })).toHaveTextContent("Calls, changes");
  await waitFor(() => expect(screen.queryByText("auto_sync_failed")).not.toBeInTheDocument());
  expect(screen.getByText("Registered filesystem")).toBeInTheDocument();
  await waitFor(() => expect(tab(/^Everything/)).toHaveTextContent("Everything3"));

  // Unticking one kind keeps the others.
  fireEvent.click(screen.getByRole("checkbox", { name: "MCP servers" }));
  expect(screen.getByRole("checkbox", { name: "Changes" })).toHaveAttribute(
    "aria-checked",
    "false",
  );
  await waitFor(() => expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument());
});

test("the agent filter lists who else made changes, with counts", async () => {
  mockApi({
    audit: [AUDIT_ENTRY, { ...AUDIT_ENTRY, id: 43, actor: "ui", resource_name: "linear" }],
    invocations: [INVOCATION],
  });
  render(wrap(<ActivityPage />));
  await screen.findByText("Registered linear");
  fireEvent.click(screen.getByRole("button", { name: /^Agent:/ }));
  const you = await screen.findByRole("checkbox", { name: "You" });
  expect(you).toHaveTextContent("1");
  expect(screen.getByRole("checkbox", { name: "Claude Code" })).toHaveTextContent("1");
  fireEvent.click(you);
  expect(screen.getByText("1 selected")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.queryByText(target("github.search_issues"))).not.toBeInTheDocument(),
  );
  expect(screen.getByText("Registered linear")).toBeInTheDocument();
  expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument();
});

test("the list says what it holds above the rows", async () => {
  mockApi({ audit: [AUDIT_ENTRY], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));
  expect(await screen.findByText("1 warning in the last hour")).toBeInTheDocument();

  openTab(/mcp calls/i);
  expect(await screen.findByText("Last hour")).toBeInTheDocument();
});

test("the MCP calls tab counts failed and denied calls", async () => {
  mockApi({
    invocations: [
      INVOCATION,
      { ...INVOCATION, id: 8, status: "error" },
      { ...INVOCATION, id: 9, status: "timeout" },
      { ...INVOCATION, id: 10, status: "denied" },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  expect(await screen.findByText("4 calls · 2 failed · 1 denied")).toBeInTheDocument();
});

test("a tab with nothing in it shows no count", async () => {
  mockApi();
  render(wrap(<ActivityPage />));
  await screen.findByText("Nothing has happened yet");
  expect(tab(/^Everything/)).toHaveTextContent(/^Everything$/);
  expect(tab(/^MCP calls/)).toHaveTextContent(/^MCP calls$/);
});

test("a log that failed on Everything names what is still shown", async () => {
  mockApi({ audit: [AUDIT_ENTRY], daemon: [DAEMON_RECORD], failing: "/mcp/invocations" });
  render(wrap(<ActivityPage />));
  const note = await screen.findByRole("status");
  expect(note).toHaveTextContent("MCP calls couldn't be loaded");
  expect(note).toHaveTextContent("Showing changes and daemon records only; they are complete.");
  expect(within(note).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByText("Changes and daemon records")).toBeInTheDocument();
});

test("the time range offers its windows and a custom range", async () => {
  mockApi({ audit: [AUDIT_ENTRY] });
  render(wrap(<ActivityPage />));
  await screen.findByText("Registered filesystem");
  const pill = screen.getByRole("button", { name: "Time range: Last hour" });
  fireEvent.click(pill);
  const options = await screen.findAllByRole("option");
  expect(options.map((o) => o.textContent)).toEqual([
    "Last 15 minutes",
    "Last hour",
    "Last 24 hours",
    "Last 7 days",
    "Everything kept",
  ]);
  expect(screen.getByRole("button", { name: "Apply range" })).toBeDisabled();
  fireEvent.click(screen.getByRole("option", { name: "Last 15 minutes" }));
  expect(
    await screen.findByRole("button", { name: "Time range: Last 15 minutes" }),
  ).toBeInTheDocument();
});

test("the daemon log opens on the last 24 hours and names its file", async () => {
  mockApi({ daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />, ["/activity?tab=daemon"]));
  expect(
    await screen.findByRole("button", { name: "Time range: Last 24 hours" }),
  ).toBeInTheDocument();
  expect(await screen.findByText("~/.coffer/logs/daemon.log")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open log file" })).toBeEnabled();
});

test("load older says what comes next and how long records are kept", async () => {
  mockApi({ audit: [AUDIT_ENTRY], olderAudit: true });
  render(wrap(<ActivityPage />, ["/activity?tab=changes"]));
  expect(await screen.findByRole("button", { name: "Load older" })).toBeInTheDocument();
  expect(
    await screen.findByText(/MCP calls are kept 30 days and changes 1 year/),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Settings › Data" })).toHaveAttribute(
    "href",
    "/settings/data",
  );
  expect(screen.getByText("1 loaded of 201")).toBeInTheDocument();
});

test("a failed call says how its server has been doing", async () => {
  mockApi({
    invocations: [{ ...INVOCATION, status: "error", error_message: "Connection refused" }],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  fireEvent.click((await screen.findByText(target("github.search_issues"))).closest("tr")!);
  const drawer = await screen.findByRole("complementary", { name: "Details" });
  await waitFor(() =>
    expect(within(drawer).getByRole("alert")).toHaveTextContent(
      /github has been failing since \d\d:\d\d — 1 error in the last 24 hours\./,
    ),
  );
  fireEvent.click(within(drawer).getByRole("button", { name: "Daemon log records" }));
  await waitFor(() => expect(tab(/daemon log/i)).toHaveAttribute("data-state", "active"));
  expect(screen.getByLabelText("Filter records")).toHaveValue("github");
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
  const drawer = await screen.findByRole("complementary", { name: "Details" });
  expect(within(drawer).getByText("Coffer")).toBeInTheDocument();
  expect(drawer.querySelector('[data-line="add"]')?.textContent).toContain("anthropic-api");
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
  await waitFor(() => expect(tab(/^Everything/)).toHaveTextContent("Everything4"));

  fireEvent.click(screen.getByRole("button", { name: /^Agent:/ }));
  fireEvent.click(await screen.findByRole("checkbox", { name: "Claude Code" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "You" }));
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("checkbox")).not.toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: /^Kind:/ }));
  fireEvent.click(await screen.findByRole("checkbox", { name: "MCP calls" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Changes" }));
  expect(screen.getByText("Everything except daemon records")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Kind:/ })).toHaveTextContent("Calls, changes");

  await waitFor(() => expect(screen.queryByText("Registered jira")).not.toBeInTheDocument());
  expect(screen.getByText("Registered linear")).toBeInTheDocument();
  expect(screen.getByText(target("github.search_issues"))).toBeInTheDocument();
  expect(screen.queryByText("auto_sync_failed")).not.toBeInTheDocument();
  await waitFor(() => expect(tab(/^Everything/)).toHaveTextContent("Everything4"));
});
