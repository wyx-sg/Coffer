// frontend/src/lib/hooks/useResourceMutations.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useEnableResource, useDisableResource, useDeleteResource } from "./useResourceMutations";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    qc,
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

describe("useEnableResource", () => {
  beforeEach(() => vi.clearAllMocks());

  test("POSTs to the enable endpoint with correct kind and name", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", name: "fs" });
    });

    expect(postMock).toHaveBeenCalledWith(
      "/resources/{kind}/{name}/enable",
      expect.objectContaining({ params: { path: { kind: "mcp_server", name: "fs" } } }),
    );
  });

  test("invalidates the resources query key on success", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useEnableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", name: "fs" });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["resources"] }),
    );
  });

  test("surfaces ApiError when POST fails so translateApiError can resolve the code", async () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "RESOURCE_NOT_FOUND", message: "not found" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnableResource(), { wrapper });

    await act(async () => {
      try {
        await result.current.mutateAsync({ kind: "mcp_server", name: "fs" });
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("RESOURCE_NOT_FOUND");
    expect(err.message).toContain("not found");
  });
});

describe("useDisableResource", () => {
  beforeEach(() => vi.clearAllMocks());

  test("POSTs to the disable endpoint", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDisableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", name: "github" });
    });

    expect(postMock).toHaveBeenCalledWith(
      "/resources/{kind}/{name}/disable",
      expect.objectContaining({ params: { path: { kind: "mcp_server", name: "github" } } }),
    );
  });

  test("invalidates the resources query key on success", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useDisableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", name: "github" });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["resources"] }),
    );
  });
});

describe("useDeleteResource", () => {
  beforeEach(() => vi.clearAllMocks());

  test("sends DELETE with correct kind and name", async () => {
    const deleteMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
    getApiClientMock.mockReturnValue({ DELETE: deleteMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDeleteResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", name: "old-server" });
    });

    expect(deleteMock).toHaveBeenCalledWith(
      "/resources/{kind}/{name}",
      expect.objectContaining({ params: { path: { kind: "mcp_server", name: "old-server" } } }),
    );
  });

  test("invalidates resources query on success", async () => {
    const deleteMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
    getApiClientMock.mockReturnValue({ DELETE: deleteMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useDeleteResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", name: "old" });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["resources"] }),
    );
  });
});
