// frontend/src/lib/hooks/useRetention.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useRetentionPolicies, useUpdateRetentionPolicy, usePruneNow } from "./useRetention";

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

describe("useRetentionPolicies", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns policies on success", async () => {
    const policies = [
      {
        table_name: "audit_log",
        display_name: "Audit log",
        description: "desc",
        default_retention_days: 90,
        retention_days: 30,
        last_pruned_at: null,
        last_pruned_rows: 0,
      },
    ];
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({ data: { policies }, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRetentionPolicies(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.policies).toHaveLength(1);
  });

  test("surfaces error on API failure", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "INTERNAL_ERROR", message: "query failed" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRetentionPolicies(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("query failed");
  });
});

describe("useUpdateRetentionPolicy", () => {
  beforeEach(() => vi.clearAllMocks());

  test("calls PATCH with the correct path and body", async () => {
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({
      PATCH: patchMock,
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateRetentionPolicy(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ tableName: "audit_log", retentionDays: 60 });
    });

    expect(patchMock).toHaveBeenCalledWith(
      "/retention/policies/{table_name}",
      expect.objectContaining({
        params: { path: { table_name: "audit_log" } },
        body: { retention_days: 60 },
      }),
    );
  });

  test("passes null (keep-forever) through to the body", async () => {
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ PATCH: patchMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateRetentionPolicy(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ tableName: "mcp_invocations", retentionDays: null });
    });

    expect(patchMock).toHaveBeenCalledWith(
      "/retention/policies/{table_name}",
      expect.objectContaining({ body: { retention_days: null } }),
    );
  });

  test("invalidates the retention query key on success", async () => {
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ PATCH: patchMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateRetentionPolicy(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ tableName: "audit_log", retentionDays: 30 });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["retention"] }),
    );
  });
});

describe("usePruneNow", () => {
  beforeEach(() => vi.clearAllMocks());

  test("calls POST /retention/prune with table_name", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: { pruned_rows: 42 },
      error: undefined,
    });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => usePruneNow(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("audit_log");
    });

    expect(postMock).toHaveBeenCalledWith(
      "/retention/prune",
      expect.objectContaining({ body: { table_name: "audit_log" } }),
    );
  });

  test("invalidates the retention query key on success", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: { pruned_rows: 0 }, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => usePruneNow(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("audit_log");
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["retention"] }),
    );
  });
});
