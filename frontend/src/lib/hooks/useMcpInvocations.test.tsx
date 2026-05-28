// frontend/src/lib/hooks/useMcpInvocations.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useMcpInvocations, useMcpServerStatus } from "./useMcpInvocations";

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

const sampleInvocations = {
  invocations: [
    {
      timestamp: "2026-05-22T12:00:00Z",
      capability_type: "tool" as const,
      capability_key: "read_file",
      duration_ms: 50,
      status: "ok" as const,
      error_message: null,
    },
  ],
};

describe("useMcpInvocations", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns invocations on success", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: sampleInvocations, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpInvocations({ serverName: "fs" }), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.invocations).toHaveLength(1);
  });

  test("surfaces error state on API failure", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "INTERNAL_ERROR", message: "db fail" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpInvocations({ serverName: "fs" }), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("db fail");
  });

  test("passes status filter and since param in query", async () => {
    const getMock = vi.fn().mockResolvedValue({ data: sampleInvocations, error: undefined });
    getApiClientMock.mockReturnValue({ GET: getMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { result } = renderHook(
      () =>
        useMcpInvocations({
          serverName: "fs",
          status: "error",
          since: "2026-05-01T00:00:00Z",
          limit: 10,
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getMock).toHaveBeenCalledWith(
      "/resources/mcp_server/{name}/invocations",
      expect.objectContaining({
        params: {
          path: { name: "fs" },
          query: expect.objectContaining({
            status: "error",
            since: "2026-05-01T00:00:00Z",
            limit: 10,
          }),
        },
      }),
    );
  });

  test("does not fetch when enabled=false", () => {
    const getMock = vi.fn();
    getApiClientMock.mockReturnValue({ GET: getMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    renderHook(() => useMcpInvocations({ serverName: "fs", enabled: false }), {
      wrapper: wrapper(),
    });
    expect(getMock).not.toHaveBeenCalled();
  });
});

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
});
