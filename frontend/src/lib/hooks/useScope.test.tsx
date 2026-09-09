// frontend/src/lib/hooks/useScope.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useResourceScope, useUpdateResourceScope } from "./useScope";
import { ApiError } from "@/lib/api/errors";

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

function stubFetch(payload: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => payload,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("useResourceScope", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("fetches GET /resources/{kind}/{name}/scope", async () => {
    const fetchMock = stubFetch({ scope: { "M-LOCAL": "*" }, axes: ["machine"] });

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useResourceScope("channel", "tg"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ scope: { "M-LOCAL": "*" }, axes: ["machine"] });
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/resources\/channel\/tg\/scope$/);
  });

  test("is disabled for an empty name", () => {
    const fetchMock = stubFetch({});
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useResourceScope("channel", ""), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useUpdateResourceScope", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("PUTs the scope body to /resources/{kind}/{name}/scope", async () => {
    const fetchMock = stubFetch({
      ref: "mcp_server:fs",
      kind: "mcp_server",
      name: "fs",
      config: {},
      scope: { "M-LOCAL": "*" },
      enabled: true,
      created_at: "2026-07-10T00:00:00Z",
      updated_at: "2026-07-10T00:00:00Z",
    });

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateResourceScope("mcp_server", "fs"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ "M-LOCAL": "*" });
    });

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/resources\/mcp_server\/fs\/scope$/);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ scope: { "M-LOCAL": "*" } });
  });

  test("invalidates the scope key and the machines list on success", async () => {
    stubFetch({ scope: null });

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateResourceScope("channel", "tg"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({});
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["scope", "channel", "tg"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["machines"] }));
  });

  test("surfaces an ApiError when the PUT fails", async () => {
    stubFetch({ error: { code: "RESOURCE_NOT_FOUND", message: "not found" } }, false, 404);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateResourceScope("channel", "missing"), { wrapper });

    await act(async () => {
      try {
        await result.current.mutateAsync({});
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("RESOURCE_NOT_FOUND");
  });
});
