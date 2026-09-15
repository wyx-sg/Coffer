// frontend/src/lib/hooks/useMcpServerMutations.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { resourcesKey } from "@/lib/api/queryKeys";
import { useImportMcpServers, useTestMcpServer } from "./useMcpServerMutations";

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

const SERVER = {
  name: "fs",
  transportType: "stdio" as const,
  command: "npx",
  args: [] as string[],
  url: "",
  env: [] as { key: string; value: string; isSecret: boolean }[],
};

describe("useImportMcpServers", () => {
  beforeEach(() => vi.clearAllMocks());

  test("registers each server and refreshes the resources cache", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);
    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useImportMcpServers(), { wrapper });

    const created = new Set<string>();
    await act(async () => {
      await result.current.mutateAsync({ servers: [SERVER], created });
    });

    expect(postMock).toHaveBeenCalledWith(
      "/resources",
      expect.objectContaining({ body: expect.objectContaining({ name: "fs" }) }),
    );
    expect(created.has("fs")).toBe(true);
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: resourcesKey }),
      ),
    );
  });

  test("skips servers this session already created", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useImportMcpServers(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ servers: [SERVER], created: new Set(["fs"]) });
    });
    expect(postMock).not.toHaveBeenCalled();
  });
});

describe("useTestMcpServer", () => {
  beforeEach(() => vi.clearAllMocks());

  test("folds a transport failure into an Error carrying the daemon's message", async () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "UPSTREAM_UNAVAILABLE", message: "connection refused" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useTestMcpServer("fs"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("connection refused");
  });
});
