// frontend/src/lib/hooks/useDaemon.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useDaemonOutOfDate, useDaemonStatus, useRestartDaemon } from "./useDaemon";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
// The skew check is a Tauri IPC call; stub it so these run in either host.
vi.mock("@/lib/tauri", () => ({
  daemonVersionMatches: vi.fn(),
  restartDaemon: vi.fn(),
  applyDaemonConnection: vi.fn(),
}));
const { daemonVersionMatches, restartDaemon, applyDaemonConnection } = await import("@/lib/tauri");
const daemonVersionMatchesMock = vi.mocked(daemonVersionMatches);
const restartDaemonMock = vi.mocked(restartDaemon);
const applyDaemonConnectionMock = vi.mocked(applyDaemonConnection);
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

describe("useRestartDaemon", () => {
  beforeEach(() => vi.clearAllMocks());

  test("installs the connection the restart returned, then refetches the whole cache", async () => {
    const connection = { baseUrl: "http://127.0.0.1:8000/api/v1", token: "fresh" };
    restartDaemonMock.mockResolvedValue({ pid: 1, started: true, ...connection } as never);
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useRestartDaemon(), {
      wrapper: ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      ),
    });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(restartDaemonMock).toHaveBeenCalledOnce();
    // The shell already waited for the replacement; taking what it handed
    // back is what keeps one restart to one daemon.
    expect(applyDaemonConnectionMock).toHaveBeenCalledWith(expect.objectContaining(connection));
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith());
    expect(applyDaemonConnectionMock.mock.invocationCallOrder[0]).toBeLessThan(
      invalidateSpy.mock.invocationCallOrder[0],
    );
  });

  test("a replacement that never answers fails the restart, and installs nothing", async () => {
    restartDaemonMock.mockRejectedValue(
      new Error("coffer-daemon (pid 1) was started but did not answer within 90s"),
    );
    const { result } = renderHook(() => useRestartDaemon(), { wrapper: wrapper() });

    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toMatch(/did not answer within/);
    // Half-applying a connection that was never confirmed would leave the app
    // calling a daemon nobody has heard from.
    expect(applyDaemonConnectionMock).not.toHaveBeenCalled();
  });
});
