// frontend/src/lib/hooks/useMcpCapabilityMutations.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useEnableCapability, useDisableCapability } from "./useMcpCapabilityMutations";
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

describe("useEnableCapability", () => {
  beforeEach(() => vi.clearAllMocks());

  test("POSTs to the enable endpoint with capability_key in the body", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnableCapability(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        serverName: "fs",
        capabilityType: "tool",
        capabilityKey: "read_file",
      });
    });

    expect(postMock).toHaveBeenCalledWith(
      "/resources/mcp_server/{name}/capabilities/{capability_type}/enable",
      expect.objectContaining({
        params: { path: { name: "fs", capability_type: "tool" } },
        body: { capability_key: "read_file" },
      }),
    );
  });

  test("invalidates the capability query key on success", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useEnableCapability(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        serverName: "fs",
        capabilityType: "tool",
        capabilityKey: "write_file",
      });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["mcp", "capabilities", "fs"] }),
    );
  });

  test("surfaces ApiError when POST fails", async () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "NOT_FOUND", message: "tool not found" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnableCapability(), { wrapper });

    await act(async () => {
      try {
        await result.current.mutateAsync({
          serverName: "fs",
          capabilityType: "tool",
          capabilityKey: "missing",
        });
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("NOT_FOUND");
    expect(err.message).toContain("tool not found");
  });
});

describe("useDisableCapability", () => {
  beforeEach(() => vi.clearAllMocks());

  test("POSTs to the disable endpoint with capability_key in the body (URI with slashes)", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDisableCapability(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        serverName: "fs",
        capabilityType: "resource",
        capabilityKey: "file:///data/path",
      });
    });

    expect(postMock).toHaveBeenCalledWith(
      "/resources/mcp_server/{name}/capabilities/{capability_type}/disable",
      expect.objectContaining({
        params: { path: { name: "fs", capability_type: "resource" } },
        body: { capability_key: "file:///data/path" },
      }),
    );
  });

  test("invalidates the capability query key on success", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useDisableCapability(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        serverName: "fs",
        capabilityType: "tool",
        capabilityKey: "read_file",
      });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["mcp", "capabilities", "fs"] }),
    );
  });
});
