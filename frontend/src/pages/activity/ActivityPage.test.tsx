// frontend/src/pages/activity/ActivityPage.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useRoutes } from "react-router-dom";
import { acceptance } from "@/test/acceptance";
import { ActivityPage } from "./ActivityPage";
import { routes } from "@/router";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

/** The page reads its tab from the URL, so every render sits under a router. */
function wrap(ui: React.ReactNode, initialEntries: string[] = ["/activity"]) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false as never } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

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
  timestamp: ago(20_000),
  resource_name: "github",
  capability_type: "tool",
  capability_key: "search_issues",
  duration_ms: 42,
  status: "ok",
  error_message: null,
  session_id: null,
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

/**
 * Mock the three records' routes (plus /daemon/status, which the shell's
 * offline banner polls) by path, so a test can see which tabs fetched. A
 * `failing` path answers with an error envelope while the others still work —
 * the older-daemon case, where one route is missing and two are not.
 */
function mockApi(
  overrides: {
    audit?: unknown[];
    invocations?: unknown[];
    daemon?: unknown[];
    failing?: string;
  } = {},
) {
  const fail = {
    data: undefined,
    error: { error: { code: "NOT_FOUND", message: "route not found" } },
  };
  const get = vi.fn().mockImplementation((path: string) => {
    if (path === overrides.failing) return Promise.resolve(fail);
    if (path === "/audit") {
      return Promise.resolve({ data: { entries: overrides.audit ?? [] }, error: undefined });
    }
    if (path === "/mcp/invocations") {
      return Promise.resolve({
        data: { invocations: overrides.invocations ?? [] },
        error: undefined,
      });
    }
    if (path === "/daemon/logs") {
      return Promise.resolve({ data: { records: overrides.daemon ?? [] }, error: undefined });
    }
    return Promise.resolve({
      data: { status: "ready", version: "0.0.0", started_at: ago(0), port: 1 },
      error: undefined,
    });
  });
  getApiClientMock.mockReturnValue({ GET: get } as unknown as ReturnType<typeof getApiClient>);
  return get;
}

/** Every path the page fetched, in call order. */
const fetchedPaths = (get: ReturnType<typeof mockApi>) =>
  get.mock.calls.map((call: unknown[]) => call[0] as string);

const fetched = (get: ReturnType<typeof mockApi>, path: string) => fetchedPaths(get).includes(path);

/** The tab triggers, named as the page labels them. */
const tab = (name: RegExp) => screen.getByRole("tab", { name });

/**
 * Switch tabs. Radix activates a trigger on mousedown (or focus), not on
 * click — firing only a click leaves the tablist exactly where it was, which
 * looks like "the other tab never queried" rather than "the test never
 * switched".
 */
const openTab = (name: RegExp) => fireEvent.mouseDown(tab(name));

/**
 * The active table's column headers, in order. DataTable renders a leading
 * headerless cell for the row-expand chevron; drop it, so these assertions
 * are about the record's own columns.
 */
const headers = () =>
  screen
    .getAllByRole("columnheader")
    .map((h) => h.textContent ?? "")
    .filter((h) => h !== "");

beforeEach(() => {
  vi.clearAllMocks();
  // Pin "now" so relative-time formatting is deterministic on slow CI.
  // `shouldAdvanceTime` keeps react-query / waitFor intervals on the real
  // clock so async assertions still settle.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date("2026-05-28T12:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ActivityPage", () => {
  test("opens on Changes, with that record's own filters", async () => {
    mockApi();
    render(wrap(<ActivityPage />));

    expect(screen.getByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(tab(/changes/i)).toHaveAttribute("data-state", "active");
    // Inline toolbar, matching the other list surfaces: no field labels.
    expect(screen.getByRole("button", { name: /all time/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /actor/i })).toBeInTheDocument();
    expect(await screen.findByText("No matching activity.")).toBeInTheDocument();
  });

  test("only the tab in front queries", async () => {
    const get = mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION] });
    render(wrap(<ActivityPage />));

    await screen.findByText("Registered filesystem");
    expect(fetched(get, "/mcp/invocations")).toBe(false);
    expect(fetched(get, "/daemon/logs")).toBe(false);

    openTab(/mcp calls/i);

    await waitFor(() => expect(fetched(get, "/mcp/invocations")).toBe(true));
    expect(fetched(get, "/daemon/logs")).toBe(false);
  });

  test("the Changes search narrows that record only", async () => {
    mockApi({ audit: [AUDIT_ENTRY] });
    render(wrap(<ActivityPage />));

    await screen.findByText("Registered filesystem");
    fireEvent.change(screen.getByLabelText(/search/i), { target: { value: "nothing-matches" } });

    await waitFor(() => {
      expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument();
    });
  });

  test("the actor filter narrows to what that actor changed", async () => {
    mockApi({ audit: [AUDIT_ENTRY] });
    render(wrap(<ActivityPage />));

    await screen.findByText("Registered filesystem");

    fireEvent.click(screen.getByRole("combobox", { name: /actor/i }));
    fireEvent.click(await screen.findByRole("option", { name: /^cli$/i }));

    await waitFor(() => {
      expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument();
    });
  });

  test("no refresh control — the page is a record, not a live console", async () => {
    mockApi({ audit: [AUDIT_ENTRY] });
    render(wrap(<ActivityPage />));

    await screen.findByText("Registered filesystem");
    expect(screen.queryByRole("button", { name: /refresh/i })).not.toBeInTheDocument();
  });

  test("the active tab lives in the URL: ?tab= opens it, switching rewrites it", async () => {
    const get = mockApi({ daemon: [DAEMON_RECORD] });
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

    expect(tab(/daemon/i)).toHaveAttribute("data-state", "active");
    await waitFor(() => expect(fetched(get, "/daemon/logs")).toBe(true));

    openTab(/mcp calls/i);
    await waitFor(() => expect(search).toBe("?tab=mcp"));

    // The default tab needs no parameter, so the URL goes back to clean.
    openTab(/changes/i);
    await waitFor(() => expect(search).toBe(""));
  });

  test("an unknown ?tab= falls back to Changes", () => {
    mockApi();
    render(wrap(<ActivityPage />, ["/activity?tab=nope"]));
    expect(tab(/changes/i)).toHaveAttribute("data-state", "active");
  });
});

acceptance("ui-shell", "activity gives each record its own tab", async () => {
  mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));

  // Changes: the plain-language line and who did it — no duration, no level.
  expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
  expect(screen.queryByText("resource_created")).not.toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Activity", "Actor"]);

  // MCP calls: the columns an invocation actually has, and the server it went
  // to — the column a per-server Invocations tab has no need of.
  openTab(/mcp calls/i);
  expect(await screen.findByText("search_issues")).toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Server", "Type", "Key", "Duration", "Status"]);
  expect(screen.getByText("github")).toBeInTheDocument();
  expect(screen.getByText("42 ms")).toBeInTheDocument();
  // Switching tab switches the record: the change is no longer on screen.
  expect(screen.queryByText("Registered filesystem")).not.toBeInTheDocument();

  // Daemon: a log line's level and logger, which nothing else here has.
  openTab(/daemon/i);
  expect(await screen.findByText("auto_sync_failed")).toBeInTheDocument();
  expect(headers()).toEqual(["Time", "Level", "Logger", "Message"]);
  expect(screen.getByText("warning")).toBeInTheDocument();
  expect(screen.getByText("coffer.sync")).toBeInTheDocument();
  expect(screen.queryByText("search_issues")).not.toBeInTheDocument();
});

acceptance("ui-shell", "activity row expands to its raw record", async () => {
  mockApi({ audit: [AUDIT_ENTRY], daemon: [DAEMON_RECORD] });
  render(wrap(<ActivityPage />));

  const line = await screen.findByText("Registered filesystem");
  fireEvent.click(line.closest("tr")!);

  // The raw record renders in a read-only CodeMirror block (tokens split
  // across spans, so assert on its text).
  await waitFor(() => {
    expect(document.querySelector(".cm-content")?.textContent).toContain(
      '"some_key": "some_value"',
    );
  });
  const raw = document.querySelector(".cm-content");
  expect(raw?.textContent).toContain('"event_type": "resource_created"');
  expect(raw?.textContent).toContain('"id": 42');

  // Clicking the same row again collapses it.
  fireEvent.click(line.closest("tr")!);
  await waitFor(() => expect(document.querySelector(".cm-content")).not.toBeInTheDocument());

  // Every tab expands the same way, to the record that tab shows.
  openTab(/daemon/i);
  const logLine = await screen.findByText("auto_sync_failed");
  fireEvent.click(logLine.closest("tr")!);
  await waitFor(() => {
    expect(document.querySelector(".cm-content")?.textContent).toContain(
      '"error": "connection refused"',
    );
  });
});

acceptance("ui-shell", "a failing record shows its error inside its own tab", async () => {
  // An older daemon serves /audit and /mcp/invocations but not /daemon/logs.
  mockApi({ audit: [AUDIT_ENTRY], invocations: [INVOCATION], failing: "/daemon/logs" });
  render(wrap(<ActivityPage />));

  expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();

  openTab(/daemon/i);
  // The envelope's code is translated for the reader; the daemon's own message
  // is not what a person is shown.
  expect(await screen.findByText("Not found.")).toBeInTheDocument();

  // The record that works is untouched — the failure did not blank the page.
  openTab(/mcp calls/i);
  expect(await screen.findByText("search_issues")).toBeInTheDocument();
  expect(screen.queryByText("Not found.")).not.toBeInTheDocument();

  openTab(/changes/i);
  expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
});

acceptance("ui-shell", "legacy /audit redirects to activity", async () => {
  mockApi();
  // The real route table under a memory router (rather than a data router:
  // react-router's data-router navigation builds a fetch Request, and jsdom's
  // AbortSignal is not the one undici's Request will accept).
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
  expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
});
