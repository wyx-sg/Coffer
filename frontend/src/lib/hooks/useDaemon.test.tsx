// frontend/src/lib/hooks/useDaemon.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useDaemonStatus } from "./useDaemon";

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
