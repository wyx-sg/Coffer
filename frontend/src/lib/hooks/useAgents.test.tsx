// frontend/src/lib/hooks/useAgents.test.tsx
//
// TanStack Query bindings for /agents. The `agentsApi` calls raw fetch
// against `${getCofferBaseUrl()}/agents/*`, so we stub `globalThis.fetch`
// rather than the typed `getApiClient` used elsewhere.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useAgents, useDetectAgents, useRegisterAgent, useRemoveAgent } from "./useAgents";

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("useAgents", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  test("returns the items array on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        items: [
          {
            name: "cur",
            type: "cursor",
            skill_dir: "/tmp/skills",
            skill_dir_override: null,
            auto_detected: false,
            enabled: true,
            description: null,
            created_at: "2026-05-22T00:00:00Z",
            updated_at: "2026-05-22T00:00:00Z",
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgents(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("cur");
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toMatch(/\/agents$/);
  });

  test("throws on a 4xx envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(500, {
          error: { code: "BOOM", message: "kaboom" },
        }),
      ),
    );
    const { result } = renderHook(() => useAgents(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("kaboom");
  });
});

describe("useRegisterAgent", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("POSTs the body and invalidates the agents query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(201, {
        name: "cur",
        type: "cursor",
        skill_dir: "/tmp/skills",
        skill_dir_override: "/tmp/skills",
        auto_detected: false,
        enabled: true,
        description: null,
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useRegisterAgent(), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({
      type: "cursor",
      name: "cur",
      skill_dir: "/tmp/skills",
      description: null,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents$/);
    expect((init as RequestInit).method).toBe("POST");
  });
});

describe("useRemoveAgent", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("DELETEs the named agent", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useRemoveAgent(), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync("cur");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur$/);
    expect((init as RequestInit).method).toBe("DELETE");
  });
});

describe("useDetectAgents", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("POSTs /agents/detect", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { registered: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useDetectAgents(), {
      wrapper: wrapper(),
    });
    const out = await result.current.mutateAsync();
    expect(out.registered).toEqual([]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/detect$/);
    expect((init as RequestInit).method).toBe("POST");
  });
});
