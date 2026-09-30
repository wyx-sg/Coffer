// src/pages/activity/ActivityPage.test.tsx — the Activity page: four tabs with counts, filters, the drawer, live insertion and holding, export.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useRoutes } from "react-router-dom";

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
const { routes } = await import("@/router");

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
            next_cursor: null,
            total: data.audit.length,
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
      if (path === "/daemon/logs") return Promise.resolve({ data: { records: data.daemon } });
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
    expect(screen.getByText("github.search_issues")).toBeInTheDocument();
  });

  test("the agent filter narrows the calls to that agent's", async () => {
    const { get } = mockApi({ invocations: [INVOCATION] });
    render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
    await screen.findByText("github.search_issues");
    fireEvent.click(screen.getByRole("button", { name: /^Agent:/ }));
    fireEvent.click(await screen.findByRole("option", { name: /Claude Code/ }));
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
  expect(await screen.findByText("github.search_issues")).toBeInTheDocument();
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

  openTab(/daemon log/i);
  fireEvent.click((await screen.findByText("auto_sync_failed")).closest("tr")!);
  const daemonDrawer = await screen.findByRole("complementary", { name: "Details" });
  await waitFor(() =>
    expect(daemonDrawer.querySelector(".cm-content")?.textContent).toContain(
      '"error": "connection refused"',
    ),
  );
});

test("a failed call opens with its error first", async () => {
  mockApi({
    invocations: [{ ...INVOCATION, status: "error", error_message: "Connection refused" }],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  fireEvent.click((await screen.findByText("github.search_issues")).closest("tr")!);
  const drawer = await screen.findByRole("complementary", { name: "Details" });
  expect(within(drawer).getByRole("alert")).toHaveTextContent("The call to github failed");
  expect(within(drawer).getByRole("alert")).toHaveTextContent("Connection refused");
  expect(within(drawer).getByRole("link", { name: "Open github" })).toHaveAttribute(
    "href",
    "/mcp-servers/u-github",
  );
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

acceptance("web-ui", "legacy /audit redirects to activity", async () => {
  mockApi();
  let path = "";
  function Probe() {
    path = useLocation().pathname;
    return null;
  }
  function AppRoutes() {
    return useRoutes(routes);
  }
  render(
    wrap(
      <>
        <AppRoutes />
        <Probe />
      </>,
      ["/audit"],
    ),
  );
  await waitFor(() => expect(path).toBe("/activity"));
  expect(await screen.findByRole("heading", { name: /Activity/ })).toBeInTheDocument();
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
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
  expect(screen.queryByText("github.search_issues")).not.toBeInTheDocument();

  openTab(/mcp calls/i);
  expect(await screen.findByText("github.search_issues")).toBeInTheDocument();
  expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument();

  openTab(/daemon log/i);
  expect(await screen.findByText("auto_sync_failed")).toBeInTheDocument();
  expect(screen.queryByText("github.search_issues")).not.toBeInTheDocument();

  expect(new Set(requested()).size).toBeGreaterThan(0);
  expect(requested().every((p) => ALLOWED.has(p))).toBe(true);
});

// revise-web-ui-ia: web-ui "new records stream in at the top" — the marker is
// added when the change is archived.
test("new records stream in at the top", async () => {
  const { data } = mockApi({ invocations: [INVOCATION] });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  await screen.findByText("github.search_issues");

  data.invocations = [
    { ...INVOCATION, id: 9, timestamp: ago(1_000), capability_key: "create_issue" },
    { ...INVOCATION, id: 8, timestamp: ago(2_000), capability_key: "list_issues" },
    INVOCATION,
  ];
  await pollHeads();

  await waitFor(() => expect(screen.getByText("github.create_issue")).toBeInTheDocument());
  const rows = within(list())
    .getAllByRole("row")
    .filter((r) => r.hasAttribute("data-record"));
  expect(rows[0]).toHaveTextContent("github.create_issue");
  expect(rows[1]).toHaveTextContent("github.list_issues");
  expect(screen.queryByRole("button", { name: /pause|resume/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /new$/ })).not.toBeInTheDocument();
});

// revise-web-ui-ia: web-ui "new records are held while the user reads".
test("new records are held while the user reads", async () => {
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

// revise-web-ui-ia: web-ui "export from the menu honours the filters".
test("export from the menu honours the filters", async () => {
  const { get } = mockApi({
    invocations: [
      { ...INVOCATION, id: 1, status: "error", error_message: "boom" },
      { ...INVOCATION, id: 2, status: "ok" },
      { ...INVOCATION, id: 3, status: "error", resource_uid: "u-linear", resource_name: "linear" },
    ],
  });
  render(wrap(<ActivityPage />, ["/activity?tab=mcp"]));
  await waitFor(() => expect(screen.getAllByText("github.search_issues").length).toBe(2));

  fireEvent.click(screen.getByRole("button", { name: /^Server:/ }));
  fireEvent.click(await screen.findByRole("option", { name: "github" }));
  // Let the first popover finish closing (it hands focus back to its pill).
  await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getAllByText("github.search_issues")).toHaveLength(2));
  fireEvent.click(screen.getByRole("button", { name: /^Status:/ }));
  fireEvent.click(await screen.findByRole("option", { name: "Error" }));
  await waitFor(() => expect(screen.getAllByText("github.search_issues")).toHaveLength(1));

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
