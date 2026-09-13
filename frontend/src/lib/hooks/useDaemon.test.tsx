// frontend/src/lib/hooks/useDaemon.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useDaemonOutOfDate, useDaemonStatus } from "./useDaemon";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
// The skew check is a Tauri IPC call; stub it so these run in either host.
vi.mock("@/lib/tauri", () => ({ daemonVersionMatches: vi.fn() }));
const { daemonVersionMatches } = await import("@/lib/tauri");
const daemonVersionMatchesMock = vi.mocked(daemonVersionMatches);
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useDaemonStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns daemon status on success", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: {
          status: "ready",
          version: "1.0.0",
          started_at: "2026-05-22T10:00:00Z",
          uptime_seconds: 120,
          upstream_summary: null,
        },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useDaemonStatus(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("ready");
  });

  test("surfaces error state on API failure", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "UNAUTHORIZED", message: "not authorized" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useDaemonStatus(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("not authorized");
  });
});

describe("useDaemonOutOfDate", () => {
  beforeEach(() => vi.clearAllMocks());

  test("stays idle until the status query has reported a version", () => {
    const { result } = renderHook(() => useDaemonOutOfDate(undefined), { wrapper: wrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(daemonVersionMatchesMock).not.toHaveBeenCalled();
  });

  test("reports out-of-date when the shell says the versions do not pair", async () => {
    daemonVersionMatchesMock.mockResolvedValue(false);
    const { result } = renderHook(() => useDaemonOutOfDate("0.1.0"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data).toBe(true));
    expect(daemonVersionMatchesMock).toHaveBeenCalledWith("0.1.0");
  });

  test("reports no skew when the versions match — the browser host always lands here", async () => {
    daemonVersionMatchesMock.mockResolvedValue(true);
    const { result } = renderHook(() => useDaemonOutOfDate("0.1.1"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(false);
  });
});
