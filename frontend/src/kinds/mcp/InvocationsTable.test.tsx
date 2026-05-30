// frontend/src/kinds/mcp/InvocationsTable.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { InvocationsTable } from "./InvocationsTable";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false as never },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const sampleInvocations = [
  {
    timestamp: new Date(Date.now() - 30_000).toISOString(), // 30 seconds ago
    capability_type: "tool" as const,
    capability_key: "read_file",
    duration_ms: 42,
    status: "ok" as const,
    error_message: null,
    session_id: null,
  },
  {
    timestamp: new Date(Date.now() - 90_000).toISOString(), // 90 seconds ago
    capability_type: "resource" as const,
    capability_key: "file://foo.txt",
    duration_ms: 500,
    status: "error" as const,
    error_message: "connection refused",
    session_id: null,
  },
];

describe("InvocationsTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders invocation rows from API data", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: { invocations: sampleInvocations },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    await waitFor(() => {
      expect(screen.getByText("read_file")).toBeInTheDocument();
    });

    expect(screen.getByText("file://foo.txt")).toBeInTheDocument();
    expect(screen.getByText("42 ms")).toBeInTheDocument();
    expect(screen.getByText("500 ms")).toBeInTheDocument();
    expect(screen.getByText("connection refused")).toBeInTheDocument();
  });

  test("clicking a row expands it to the invocation's raw log JSON", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: { invocations: sampleInvocations },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    const keyCell = await screen.findByText("read_file");
    const findRaw = () => screen.queryByText((_, el) => el?.tagName === "PRE");

    // Collapsed by default.
    expect(findRaw()).not.toBeInTheDocument();

    // Expand → the row's full underlying JSON record is shown.
    fireEvent.click(keyCell.closest("tr")!);
    await waitFor(() => {
      expect(findRaw()?.textContent).toContain('"capability_key": "read_file"');
    });
    expect(findRaw()?.textContent).toContain('"status": "ok"');

    // Collapse again.
    fireEvent.click(keyCell.closest("tr")!);
    await waitFor(() => expect(findRaw()).not.toBeInTheDocument());
  });

  test("an expanded row stays expanded when a client-side filter reorders the list", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: { invocations: sampleInvocations },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    const keyCell = await screen.findByText("file://foo.txt");
    const findRaw = () => screen.queryByText((_, el) => el?.tagName === "PRE");

    // Expand the SECOND row (index 1 in the full fetched list).
    fireEvent.click(keyCell.closest("tr")!);
    await waitFor(() => {
      expect(findRaw()?.textContent).toContain('"capability_key": "file://foo.txt"');
    });

    // Narrow the search so that row becomes index 0 of the filtered view. Its
    // identity (and thus its expanded state) must survive the reorder.
    const searchInput = screen.getByPlaceholderText("Search invocations");
    fireEvent.change(searchInput, { target: { value: "foo" } });

    expect(screen.queryByText("read_file")).not.toBeInTheDocument();
    expect(findRaw()?.textContent).toContain('"capability_key": "file://foo.txt"');
  });

  test("renders empty state when no invocations", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: { invocations: [] },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    await waitFor(() => {
      expect(screen.getByText("No invocations yet.")).toBeInTheDocument();
    });
  });

  test("shows error state and retry button on API failure", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "INTERNAL", message: "server exploded" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    await waitFor(() => {
      expect(screen.getByText("server exploded")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  // ── NEW filter tests ──────────────────────────────────────────────────────

  test("search box narrows rows by capability_key (case-insensitive)", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: { invocations: sampleInvocations },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    // Wait for rows to appear
    await waitFor(() => {
      expect(screen.getByText("read_file")).toBeInTheDocument();
    });
    expect(screen.getByText("file://foo.txt")).toBeInTheDocument();

    // Type in the search box — only "read_file" should remain visible
    const searchInput = screen.getByPlaceholderText("Search invocations");
    fireEvent.change(searchInput, { target: { value: "read" } });

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.queryByText("file://foo.txt")).not.toBeInTheDocument();
  });

  test("selecting Error status triggers refetch with status=error query param", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: { invocations: sampleInvocations },
      error: undefined,
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText("read_file")).toBeInTheDocument();
    });

    // Open the Status combobox and select "Error"
    // The status combobox is the one with aria-label containing "Status"
    const statusTrigger = screen.getByRole("combobox", { name: /status/i });
    fireEvent.click(statusTrigger);

    // Wait for the dropdown to open and click the Error option
    const errorOption = await screen.findByRole("option", { name: /^error$/i });
    fireEvent.click(errorOption);

    // Wait for the API call to include status=error
    await waitFor(() => {
      const calls = getMock.mock.calls;
      const errorCall = calls.find((call: unknown[]) => {
        const [, opts] = call as [string, { params?: { query?: Record<string, unknown> } }];
        return opts?.params?.query?.status === "error";
      });
      expect(errorCall).toBeDefined();
    });
  });

  test("selecting Last 1 hour triggers refetch with since ~= now-1h", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: { invocations: sampleInvocations },
      error: undefined,
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText("read_file")).toBeInTheDocument();
    });

    // Click on the time range picker trigger and pick "Last 1 hour"
    const timeRangeButton = screen.getByRole("button", { name: /all time/i });
    fireEvent.click(timeRangeButton);

    // Wait for popover to open with preset options
    const oneHourOption = await screen.findByRole("button", { name: /last 1 hour/i });
    const beforeClick = Date.now();
    await act(async () => {
      fireEvent.click(oneHourOption);
    });

    // Wait for the API call that includes a `since` param close to now-1h
    const oneHourAgo = beforeClick - 3_600_000;
    await waitFor(() => {
      const calls = getMock.mock.calls;
      const rangeCall = calls.find((call: unknown[]) => {
        const [, opts] = call as [string, { params?: { query?: Record<string, unknown> } }];
        const since = opts?.params?.query?.since;
        if (typeof since !== "string") return false;
        const sinceMs = new Date(since).getTime();
        // Within a 60-second tolerance of now-1h
        return Math.abs(sinceMs - oneHourAgo) < 60_000;
      });
      expect(rangeCall).toBeDefined();
    });
  });

  test("shows no-matches message when filters exclude all rows", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: { invocations: sampleInvocations },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<InvocationsTable serverName="fs" />));

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText("read_file")).toBeInTheDocument();
    });

    // Type something that matches nothing
    const searchInput = screen.getByPlaceholderText("Search invocations");
    fireEvent.change(searchInput, { target: { value: "zzz_no_match" } });

    // Should show the "no matches" message, NOT the "no invocations" empty state
    await waitFor(() => {
      expect(screen.getByText("No invocations match your filters.")).toBeInTheDocument();
    });
    expect(screen.queryByText("No invocations yet.")).not.toBeInTheDocument();
  });
});
