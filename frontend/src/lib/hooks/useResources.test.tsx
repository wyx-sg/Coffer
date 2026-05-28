// frontend/src/lib/hooks/useResources.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useResources } from "./useResources";
import { mockApiClient } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

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

describe("useResources", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("returns the resources array on success", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: {
          resources: [
            {
              ref: "mcp_server:fs",
              kind: "mcp_server",
              name: "fs",
              description: null,
              config: {},
              enabled: true,
              created_at: "2026-05-21T00:00:00Z",
              updated_at: "2026-05-21T00:00:00Z",
            },
          ],
        },
        error: undefined,
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useResources("mcp_server"), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("fs");
  });

  test("throws on API error", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "BOOM", message: "kaboom" } },
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useResources(), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect((result.current.error as Error).message).toContain("kaboom");
  });
});
