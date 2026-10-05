// frontend/src/lib/hooks/useAgentConfig.test.tsx
//
// Covers the v2 agent config-file + Coffer-MCP-install hooks that the
// AgentDetailPage drives. Like useAgents.test.tsx these go through the typed
// client, so we stub `globalThis.fetch` and
// assert URL shaping, method, body, gating, and cache invalidation.
//
// Every one of those routes is addressed by the agent's `uid`, so the fixtures
// carry a uid (`u-cur`) that deliberately differs from the label (`cur`): the
// URL and the query key must spell the uid, and only the rendered record ever
// spells the name.

import { afterEach, describe, expect, test, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { resetApiClient } from "@/lib/api/client";
import type { PropsWithChildren } from "react";
import {
  useAgent,
  usePatchAgent,
  useAgentConfigFiles,
  useAgentConnection,
  useAgentConnect,
} from "./useAgents";

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function wrapperFor(qc: QueryClient) {
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

// The typed client keeps the `fetch` it was built with; each test stubs its own.
beforeEach(() => resetApiClient());
afterEach(() => vi.unstubAllGlobals());

describe("useAgent", () => {
  test("GETs the agent the uid names and is gated on a non-empty uid", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        uid: "u-cur",
        name: "cur",
        type: "codex",
        config_dir: "/home/u/.codex",
        description: null,
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    // Empty uid → query disabled, no fetch.
    const disabled = renderHook(() => useAgent(""), { wrapper: wrapperFor(makeClient()) });
    expect(disabled.result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();

    const { result } = renderHook(() => useAgent("u-cur"), { wrapper: wrapperFor(makeClient()) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe("cur");
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(/\/agents\/u-cur$/);
  });
});

describe("usePatchAgent", () => {
  test("PATCHes the agent the uid names with the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        uid: "u-cur",
        name: "cur",
        type: "codex",
        config_dir: "/new/dir",
        description: "d",
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => usePatchAgent(), { wrapper: wrapperFor(makeClient()) });
    await result.current.mutateAsync({ uid: "u-cur", body: { config_dir: "/new/dir" } });

    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-cur$/);
    expect(request.method).toBe("PATCH");
    expect(await request.clone().json()).toEqual({ config_dir: "/new/dir" });
  });
});

describe("useAgentConfigFiles", () => {
  test("GETs the config-files list and is gated on a uid", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        items: [
          {
            key: "settings",
            display_name: "settings.json",
            path: "/home/u/.codex/settings.json",
            format: "json",
            exists: true,
            size: 12,
            modified_at: "2026-05-22T00:00:00Z",
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const off = renderHook(() => useAgentConfigFiles(""), { wrapper: wrapperFor(makeClient()) });
    expect(off.result.current.fetchStatus).toBe("idle");

    const { result } = renderHook(() => useAgentConfigFiles("u-cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].key).toBe("settings");
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(/\/agents\/u-cur\/config-files$/);
  });
});

describe("useAgentConnection", () => {
  test("GETs the Coffer connection and is gated on a uid", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { state: "disconnected", parts: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const off = renderHook(() => useAgentConnection(""), { wrapper: wrapperFor(makeClient()) });
    expect(off.result.current.fetchStatus).toBe("idle");

    const { result } = renderHook(() => useAgentConnection("u-cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.state).toBe("disconnected");
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(
      /\/agents\/u-cur\/coffer-connection$/,
    );
  });
});

describe("useAgentConnect", () => {
  test("POSTs to connect when given true and stores the answer as the status", async () => {
    const answer = {
      state: "connected",
      parts: [{ key: "mcp", installed: true, detail: "/opt/coffer-mcp-shim" }],
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, answer));
    vi.stubGlobal("fetch", fetchMock);

    const qc = makeClient();
    const { result } = renderHook(() => useAgentConnect("u-cur"), { wrapper: wrapperFor(qc) });
    await result.current.mutateAsync(true);

    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-cur\/coffer-connection$/);
    expect(request.method).toBe("POST");
    expect(qc.getQueryData(["agents", "u-cur", "coffer-connection"])).toEqual(answer);
  });

  test("DELETEs to disconnect when given false", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { state: "disconnected", parts: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgentConnect("u-cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await result.current.mutateAsync(false);

    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-cur\/coffer-connection$/);
    expect(request.method).toBe("DELETE");
  });
});
