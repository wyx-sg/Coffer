// frontend/src/lib/hooks/useAudit.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useAudit } from "./useAudit";
import { mockApiClient } from "@/test/mockApiClient";

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

describe("useAudit", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns entries array on success", async () => {
    const entries = [
      {
        id: 1,
        timestamp: "2026-05-22T12:00:00Z",
        event_type: "resource_created",
        resource_kind: "mcp_server",
        resource_name: "fs",
        actor: "api",
        details: null,
      },
    ];
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: { entries }, error: undefined }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useAudit({ limit: 10 }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.entries).toHaveLength(1);
    expect(result.current.data?.entries[0].event_type).toBe("resource_created");
  });

  test("surfaces error state on API failure", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "INTERNAL_ERROR", message: "db error" } },
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useAudit({}), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("db error");
  });

  test("passes filter params to the GET call", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: { entries: [] }, error: undefined }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(
      () =>
        useAudit({
          kind: "mcp_server",
          name: "fs",
          eventType: "resource_created",
          since: "2026-05-01T00:00:00Z",
          limit: 25,
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.GET).toHaveBeenCalledWith(
      "/audit",
      expect.objectContaining({
        params: {
          query: expect.objectContaining({
            kind: "mcp_server",
            name: "fs",
            event_type: "resource_created",
            since: "2026-05-01T00:00:00Z",
            limit: 25,
          }),
        },
      }),
    );
  });
});
