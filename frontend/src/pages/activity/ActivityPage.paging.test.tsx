// src/pages/activity/ActivityPage.paging.test.tsx — Activity opens on one small page of the open tab and grows as it is read.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/events/eventStream", () => ({
  followDaemonEvents: (_: unknown, signal: AbortSignal) =>
    new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve())),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));

const { getApiClient } = await import("@/lib/api/client");
const { ActivityPage } = await import("./ActivityPage");

const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

const entry = (id: number) => ({
  id,
  timestamp: ago(id * 1000),
  event_type: "resource_created",
  resource_kind: "mcp_server",
  resource_name: `server-${id}`,
  actor: "api",
  details: null,
  trace_id: null,
  conversation_id: null,
  turn_id: null,
});

type Query = Record<string, unknown>;
type Init = { params?: { query?: Query }; signal?: AbortSignal };

/** 100 audit rows, served by cursor: the cursor is the id of the last row of the page before. */
function mockApi(opts: { hang?: (q: Query) => boolean } = {}) {
  const all = Array.from({ length: 100 }, (_, i) => entry(i + 1));
  const get = vi.fn().mockImplementation((path: string, init?: Init) => {
    const query = init?.params?.query ?? {};
    if (opts.hang?.(query)) {
      return new Promise((_, reject) =>
        init?.signal?.addEventListener("abort", () => reject(new DOMException("x", "AbortError"))),
      );
    }
    if (path === "/audit") {
      const rows = all.filter((r) => !query.q || r.resource_name.includes(String(query.q)));
      const from = query.cursor ? Number(query.cursor) : 0;
      const limit = Number(query.limit);
      const page = rows.slice(from, from + limit);
      return Promise.resolve({
        data: {
          entries: page,
          next_cursor: from + limit < rows.length ? String(from + limit) : null,
          total: rows.length,
        },
      });
    }
    if (path === "/mcp/invocations") {
      return Promise.resolve({ data: { invocations: [], next_cursor: null, total: 0 } });
    }
    if (path === "/daemon/logs") {
      return Promise.resolve({
        data: { records: [], next_cursor: null, total: 0, total_is_floor: false, path: "/d.log" },
      });
    }
    return Promise.resolve({ data: { resources: [], policies: [] } });
  });
  vi.mocked(getApiClient).mockReturnValue({ GET: get } as unknown as ReturnType<
    typeof getApiClient
  >);
  return get;
}

/** Every request to `path`, as its query. */
const queries = (get: ReturnType<typeof mockApi>, path: string) =>
  get.mock.calls.filter((c) => c[0] === path).map((c) => (c[1] as Init).params?.query ?? {});

function wrap(initial = "/activity?tab=changes") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false as never } },
  });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[initial]}>
          <ActivityPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

const rows = () => document.querySelectorAll("tr[data-record]").length;

let observers: { callback: IntersectionObserverCallback; target: Element }[] = [];

beforeEach(() => {
  observers = [];
  vi.clearAllMocks();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private callback: IntersectionObserverCallback) {}
      observe(target: Element) {
        observers.push({ callback: this.callback, target });
      }
      disconnect() {
        observers = observers.filter((o) => o.callback !== this.callback);
      }
      unobserve() {}
      takeRecords() {
        return [];
      }
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

const scrollToEnd = () =>
  act(() => {
    for (const o of observers) {
      o.callback(
        [{ isIntersecting: true, target: o.target } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
    }
  });

test("it opens on one small page: 30 rows of the open tab, and the rest of the log unread", async () => {
  const get = mockApi();
  render(wrap());
  await waitFor(() => expect(rows()).toBe(30));
  const pages = queries(get, "/audit").filter((q) => q.limit === 30);
  expect(pages).toHaveLength(1);
  expect(pages[0].cursor).toBeUndefined();
  // The other logs are not read for their rows (a one-row read is a tab's count).
  expect(queries(get, "/mcp/invocations").every((q) => q.limit === 1)).toBe(true);
  expect(queries(get, "/daemon/logs").every((q) => q.limit === 1)).toBe(true);
  expect(screen.getAllByText(/30 loaded/).length).toBeGreaterThan(0);
});

test("scrolling to the end loads the next 50 by cursor, with 'N loaded' under the rows", async () => {
  const get = mockApi();
  render(wrap());
  await waitFor(() => expect(rows()).toBe(30));
  await scrollToEnd();
  await waitFor(() => expect(rows()).toBe(80));
  const next = queries(get, "/audit").find((q) => q.cursor !== undefined);
  expect(next).toMatchObject({ limit: 50, cursor: "30" });
  expect(screen.getAllByText(/80 loaded/).length).toBeGreaterThan(0);
  await scrollToEnd();
  await waitFor(() => expect(rows()).toBe(100));
  await waitFor(() =>
    expect(screen.getByText(/everything in this time range/)).toBeInTheDocument(),
  );
});

test("'Load more' does the same by hand, for a reader who cannot scroll", async () => {
  mockApi();
  render(wrap());
  await waitFor(() => expect(rows()).toBe(30));
  fireEvent.click(screen.getByRole("button", { name: "Load older" }));
  await waitFor(() => expect(rows()).toBe(80));
});

test("search is the route's: debounced into one request, and the stale one is abandoned", async () => {
  // The first search request never answers; typing on aborts it.
  const get = mockApi({ hang: (q) => q.q === "server-1" });
  render(wrap());
  await waitFor(() => expect(rows()).toBe(30));
  const box = screen.getByLabelText("Filter records");
  fireEvent.change(box, { target: { value: "server-1" } });
  await waitFor(() => expect(queries(get, "/audit").some((q) => q.q === "server-1")).toBe(true));
  const stale = get.mock.calls.find(
    (c) => c[0] === "/audit" && (c[1] as Init).params?.query?.q === "server-1",
  )?.[1] as Init;
  fireEvent.change(box, { target: { value: "server-2" } });
  await waitFor(() => expect(stale.signal?.aborted).toBe(true));
  // Server-side: the rows that arrive are the route's matches, from the first page again.
  await waitFor(() => expect(rows()).toBe(11));
  const first = queries(get, "/audit").filter((q) => q.q === "server-2" && q.limit === 30);
  expect(first).toHaveLength(1);
  expect(first[0].cursor).toBeUndefined();
  // Typing "server-1" then "server-2" in quick succession never asked for the keystrokes between.
  expect(queries(get, "/audit").some((q) => q.q === "server-")).toBe(false);
});
