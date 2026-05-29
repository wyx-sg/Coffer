// frontend/src/pages/observability/ObservabilityPage.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ObservabilityPage } from "./ObservabilityPage";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("ObservabilityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Pin "now" so any relative-time formatting (e.g. "30 seconds ago")
    // is deterministic across runs — previously the assertions implicitly
    // depended on real-clock drift, which surfaced as flakes on slow CI.
    // `shouldAdvanceTime: true` keeps React Query / waitFor intervals
    // running on the underlying real clock so async assertions still
    // settle while Date.now() returns our pinned timestamp.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-05-28T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("shows the heading and the time + actor filters", () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: { entries: [] }, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    expect(screen.getByRole("heading", { name: "Audit log" })).toBeInTheDocument();
    expect(screen.getByText("Time range")).toBeInTheDocument();
    expect(screen.getByText("Actor")).toBeInTheDocument();
  });

  test("shows empty state when the audit log returns no entries", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: { entries: [] }, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    expect(await screen.findByText("No matching audit entries.")).toBeInTheDocument();
  });

  test("renders each audit row as a plain-language activity line", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: {
          entries: [
            {
              id: 1,
              timestamp: new Date(Date.now() - 30_000).toISOString(),
              event_type: "resource_created",
              resource_kind: "mcp_server",
              resource_name: "filesystem",
              actor: "api",
              details: null,
            },
          ],
        },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    // The raw event_type code is translated into a human sentence.
    expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
    // The actor code is humanised too (api -> API).
    expect(screen.getByText("API")).toBeInTheDocument();
  });

  test("shows an error message on API failure", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "UNAUTHORIZED", message: "not authorized" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    expect(await screen.findByText("not authorized")).toBeInTheDocument();
  });

  test("clicking a row expands it and reveals the raw log JSON", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: {
          entries: [
            {
              id: 42,
              timestamp: new Date(Date.now() - 10_000).toISOString(),
              event_type: "resource_created",
              resource_kind: "mcp_server",
              resource_name: "github",
              actor: "api",
              details: { some_key: "some_value" },
            },
          ],
        },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    // Wait for the row to render
    const activityCell = await screen.findByText("Registered github");
    // Click the row to expand it
    fireEvent.click(activityCell.closest("tr")!);

    // The raw log panel shows the entry's full underlying JSON record.
    const raw = await screen.findByText((_, el) => el?.tagName === "PRE");
    expect(raw.textContent).toContain('"some_key": "some_value"');
    expect(raw.textContent).toContain('"event_type": "resource_created"');
    expect(raw.textContent).toContain('"id": 42');
  });

  test("clicking the expanded row again collapses it", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: {
          entries: [
            {
              id: 7,
              timestamp: new Date(Date.now() - 5_000).toISOString(),
              event_type: "daemon_started",
              resource_kind: null,
              resource_name: null,
              actor: "system",
              details: { note: "hello" },
            },
          ],
        },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    const activityCell = await screen.findByText("Daemon started");
    const row = activityCell.closest("tr")!;

    // Expand
    fireEvent.click(row);
    const findRaw = () => screen.queryByText((_, el) => el?.tagName === "PRE");
    await waitFor(() => expect(findRaw()?.textContent).toContain('"note": "hello"'));

    // Collapse — click the same row again
    fireEvent.click(row);
    await waitFor(() => expect(findRaw()).not.toBeInTheDocument());
  });

  test("free-text search filter narrows the visible rows", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: {
          entries: [
            {
              id: 1,
              timestamp: new Date(Date.now() - 30_000).toISOString(),
              event_type: "resource_created",
              resource_kind: "mcp_server",
              resource_name: "filesystem",
              actor: "api",
              details: null,
            },
            {
              id: 2,
              timestamp: new Date(Date.now() - 20_000).toISOString(),
              event_type: "resource_enabled",
              resource_kind: "mcp_server",
              resource_name: "github",
              actor: "ui",
              details: null,
            },
          ],
        },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    // Both rows visible initially
    expect(await screen.findByText("Registered filesystem")).toBeInTheDocument();
    expect(screen.getByText("Enabled github")).toBeInTheDocument();

    // Type in the search box
    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, { target: { value: "filesystem" } });

    // Only the filesystem row should remain
    await waitFor(() => {
      expect(screen.queryByText("Enabled github")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Registered filesystem")).toBeInTheDocument();
  });

  test("pagination controls move between pages", async () => {
    // Create 25 entries to force page 2 at pageSize=20
    const entries = Array.from({ length: 25 }, (_, i) => ({
      id: i + 1,
      timestamp: new Date(Date.now() - i * 1000).toISOString(),
      event_type: "resource_created",
      resource_kind: "mcp_server",
      resource_name: `server-${i + 1}`,
      actor: "api",
      details: null,
    }));

    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: { entries }, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<ObservabilityPage />));

    // Page 1: first entry visible (most recent first)
    expect(await screen.findByText("Registered server-1")).toBeInTheDocument();
    // Entry 21 is NOT on page 1
    expect(screen.queryByText("Registered server-21")).not.toBeInTheDocument();

    // Click Next to go to page 2
    fireEvent.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(screen.getByText("Registered server-21")).toBeInTheDocument();
    });
    // Entry 1 is no longer visible on page 2
    expect(screen.queryByText("Registered server-1")).not.toBeInTheDocument();
  });
});
