// frontend/src/pages/activity/DaemonTab.test.tsx
//
// The Daemon tab's own rules — the ones the old merged timeline carried and
// that are about the daemon log itself: where a line that is not a structlog
// record gets its time from, and what a line with no time at all renders as.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DaemonTab } from "./DaemonTab";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function mockLogs(records: unknown[]) {
  const get = vi.fn().mockResolvedValue({ data: { records }, error: undefined });
  getApiClientMock.mockReturnValue({ GET: get } as unknown as ReturnType<typeof getApiClient>);
  return get;
}

/** The query the tab sent with its last /daemon/logs request. */
function lastQuery(get: ReturnType<typeof mockLogs>) {
  const call = get.mock.calls.at(-1) as [string, { params: { query: Record<string, unknown> } }];
  return call[1].params.query;
}

/**
 * The row carrying this text, and its four cells. DataTable renders a leading
 * cell holding the row-expand chevron; drop it, or every assertion here would
 * compare two empty strings and pass without looking at the row.
 */
function cellsOf(text: string | RegExp) {
  const row = screen.getByText(text).closest("tr")!;
  return within(row)
    .getAllByRole("cell")
    .map((c) => c.textContent ?? "")
    .slice(1);
}

// The tail comes back newest-first, and a traceback is written to the file
// immediately AFTER the record that raised it — so reversed, the traceback
// lands at the LOWER index and the record it belongs to at the higher one.
const TRACEBACK = {
  timestamp: null,
  level: null,
  event: null,
  record: { raw: "Traceback (most recent call last):" },
};
const RAISED = {
  timestamp: "2026-05-28T11:59:00Z",
  level: "error",
  event: "sync_failed",
  record: { event: "sync_failed", level: "error", logger: "coffer.sync" },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DaemonTab", () => {
  test("an undated line borrows the timestamp of the record it belongs to", async () => {
    mockLogs([TRACEBACK, RAISED]);
    render(wrap(<DaemonTab enabled />));

    await screen.findByText("sync_failed");
    const [tracebackTime] = cellsOf(/^Traceback/);
    const [recordTime] = cellsOf("sync_failed");

    expect(tracebackTime).toBe(recordTime);
    expect(tracebackTime).not.toBe("—");
  });

  test("a line with nothing to borrow renders a dash, not the epoch", async () => {
    mockLogs([TRACEBACK]);
    render(wrap(<DaemonTab enabled />));

    const cells = await waitFor(() => cellsOf(/^Traceback/));
    // Time, level and logger are all things this line does not have; none of
    // them is invented, and none reads 1970.
    expect(cells).toEqual(["—", "—", "—", "Traceback (most recent call last):"]);
  });

  test("the level floor narrows the fetch itself", async () => {
    // A floor, not a toggle: picking Warnings must ask the daemon for
    // warnings AND the errors among them, not filter the page it already has
    // — the tail it fetched may hold no warning at all.
    const get = mockLogs([RAISED]);
    render(wrap(<DaemonTab enabled />));

    await screen.findByText("sync_failed");
    expect(lastQuery(get).level).toBeUndefined();

    // jsdom has no PointerEvent; open the Radix listbox from the keyboard.
    fireEvent.keyDown(screen.getByRole("combobox", { name: /log level/i }), { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: /warnings and errors/i }));

    await waitFor(() => expect(lastQuery(get).level).toBe("warning"));
  });

  test("every level is the default and sends no floor at all", async () => {
    const get = mockLogs([RAISED]);
    render(wrap(<DaemonTab enabled />));

    await screen.findByText("sync_failed");
    expect(screen.getByRole("combobox", { name: /log level/i })).toHaveTextContent(/all levels/i);
    expect(lastQuery(get).level).toBeUndefined();
  });

  test("the search matches the logger as well as the message", async () => {
    mockLogs([RAISED]);
    render(wrap(<DaemonTab enabled />));

    await screen.findByText("sync_failed");
    fireEvent.change(screen.getByLabelText(/search/i), { target: { value: "coffer.sync" } });
    expect(screen.getByText("sync_failed")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/search/i), { target: { value: "coffer.chat" } });
    await waitFor(() => expect(screen.queryByText("sync_failed")).not.toBeInTheDocument());
  });

  test("a tab that is not in front fetches nothing", async () => {
    const get = mockLogs([RAISED]);
    render(wrap(<DaemonTab enabled={false} />));

    await screen.findByText("No matching log records.");
    expect(get).not.toHaveBeenCalled();
  });
});
