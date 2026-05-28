// frontend/src/lib/hooks/useMcpCapabilities.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useMcpCapabilities } from "./useMcpCapabilities";

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

const sampleCapabilities = {
  tools: [
    {
      original_name: "read_file",
      prefixed_name: "fs__read_file",
      description: "Read",
      enabled: true,
      input_schema: null,
    },
  ],
  resources: [],
  prompts: [],
};

describe("useMcpCapabilities", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns capability list on success", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: sampleCapabilities, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpCapabilities("fs"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tools).toHaveLength(1);
    expect(result.current.data?.tools?.[0].original_name).toBe("read_file");
  });

  test("surfaces error state on API failure", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "UPSTREAM_UNAVAILABLE", message: "upstream down" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpCapabilities("fs"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("upstream down");
  });

  test("passes the server name in the path params", async () => {
    const getMock = vi.fn().mockResolvedValue({ data: sampleCapabilities, error: undefined });
    getApiClientMock.mockReturnValue({ GET: getMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { result } = renderHook(() => useMcpCapabilities("github"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getMock).toHaveBeenCalledWith(
      "/resources/mcp_server/{name}/capabilities",
      expect.objectContaining({ params: { path: { name: "github" } } }),
    );
  });

  test("does NOT fetch when enabled=false", () => {
    const getMock = vi.fn();
    getApiClientMock.mockReturnValue({ GET: getMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    renderHook(() => useMcpCapabilities("fs", false), { wrapper: wrapper() });
    expect(getMock).not.toHaveBeenCalled();
  });

  test("starts in the loading state before the response arrives", async () => {
    type ResolveFn = (value: { data: unknown; error: unknown }) => void;
    // Initialized inside the Promise executor below; the closure assignment
    // is invisible to TS narrowing so we widen the declared type.
    let resolveFn: ResolveFn | null = null;
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(
        new Promise<{ data: unknown; error: unknown }>((resolve) => {
          resolveFn = resolve;
        }),
      ),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpCapabilities("fs"), { wrapper: wrapper() });
    // While the GET promise is unresolved, react-query reports isPending=true
    // (alias for isLoading in v5). This pins the loading branch so a
    // refactor that drops the `enabled` gate is caught.
    expect(result.current.isPending).toBe(true);
    expect(result.current.data).toBeUndefined();
    // Resolve to avoid leaking the pending promise into the next test.
    (resolveFn as ResolveFn | null)?.({ data: sampleCapabilities, error: undefined });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  test("treats an empty (data: undefined / error: undefined) response as an error", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpCapabilities("fs"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("empty capability response");
  });

  test("falls back to UPSTREAM_UNAVAILABLE when the error envelope lacks a code", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: {} },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useMcpCapabilities("fs"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    // The hook coerces missing code/message via `??` — assert the
    // default-branch message lands rather than the user-facing copy.
    expect((result.current.error as Error).message).toContain("list capabilities failed");
  });
});
