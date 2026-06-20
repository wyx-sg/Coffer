// frontend/src/lib/hooks/useDaemon.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useDaemonStatus, useVaultBackup } from "./useDaemon";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
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

describe("useVaultBackup", () => {
  beforeEach(() => vi.clearAllMocks());

  test("mutation calls POST /vault/backup with no body and returns data", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: { path: "/home/user/.coffer/backups/coffer-20260522T120000.tar.gz", size_bytes: 4096 },
      error: undefined,
    });
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useVaultBackup(), { wrapper: wrapper() });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(postMock).toHaveBeenCalledWith("/vault/backup", {});
  });

  test("surfaces error when POST fails", async () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "INTERNAL_ERROR", message: "disk full" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useVaultBackup(), { wrapper: wrapper() });

    await act(async () => {
      try {
        await result.current.mutateAsync();
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("disk full");
  });
});
