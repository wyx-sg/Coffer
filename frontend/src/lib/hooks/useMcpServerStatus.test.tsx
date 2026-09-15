// frontend/src/lib/hooks/useMcpServerStatus.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useMcpServerRunner, useMcpServerStatus } from "./useMcpServerStatus";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useMcpServerStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns 'healthy' when backend reports healthy", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: { status: "healthy" }, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpServerStatus("fs"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe("healthy");
  });

  test("returns null when backend reports unknown (no badge should show)", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: { status: "unknown" }, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpServerStatus("fs"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });

  test("returns null on API error (graceful degradation)", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "NOT_FOUND", message: "server missing" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpServerStatus("fs"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });

  test("the health and runner hooks share ONE /status read per server", async () => {
    // The list page mounts both per row; two keys over the same endpoint used
    // to cost two requests per server.
    const get = vi
      .fn()
      .mockResolvedValue({ data: { status: "healthy", missing_runner: "npx" }, error: undefined });
    getApiClientMock.mockReturnValue({ GET: get } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(
      () => ({ status: useMcpServerStatus("fs"), runner: useMcpServerRunner("fs") }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.runner.isSuccess).toBe(true));
    expect(result.current.status.data).toBe("healthy");
    expect(result.current.runner.data).toEqual({ missingRunner: "npx" });
    expect(get).toHaveBeenCalledTimes(1);
  });
});
