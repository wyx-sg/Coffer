// frontend/src/lib/hooks/useAgentConfig.test.tsx
//
// Covers the v2 agent config-file + Coffer-MCP-install hooks that the
// AgentDetailPage drives. Like useAgents.test.tsx these call raw `fetch`
// against `${getCofferBaseUrl()}/agents/*`, so we stub `globalThis.fetch` and
// assert URL shaping, method, body, gating, and cache invalidation.
//
// Every one of those routes is addressed by the agent's `uid`, so the fixtures
// carry a uid (`u-cur`) that deliberately differs from the label (`cur`): the
// URL and the query key must spell the uid, and only the rendered record ever
// spells the name.

import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import {
  useAgent,
  usePatchAgent,
  useAgentConfigFiles,
  useAgentConfigFile,
  useAgentMcpStatus,
  useAgentMcpInstall,
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
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/u-cur$/);
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

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/u-cur$/);
    expect((init as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ config_dir: "/new/dir" });
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
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/u-cur\/config-files$/);
  });
});

describe("useAgentConfigFile", () => {
  test("GETs one config file and stays idle until both uid and key are present", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        key: "settings",
        format: "json",
        exists: true,
        content: "{}",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    // null key → disabled.
    const off = renderHook(() => useAgentConfigFile("u-cur", null), {
      wrapper: wrapperFor(makeClient()),
    });
    expect(off.result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();

    const { result } = renderHook(() => useAgentConfigFile("u-cur", "settings"), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.content).toBe("{}");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/u-cur\/config-files\/settings$/);
  });
});

describe("useAgentMcpStatus", () => {
  test("GETs the mcp-install status and is gated on a uid", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { installed: false, command: null }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const off = renderHook(() => useAgentMcpStatus(""), { wrapper: wrapperFor(makeClient()) });
    expect(off.result.current.fetchStatus).toBe("idle");

    const { result } = renderHook(() => useAgentMcpStatus("u-cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.installed).toBe(false);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/u-cur\/mcp-install$/);
  });
});

describe("useAgentMcpInstall", () => {
  test("POSTs to install when given true and invalidates the status query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { installed: true, command: "coffer mcp" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const qc = makeClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useAgentMcpInstall("u-cur"), { wrapper: wrapperFor(qc) });
    await result.current.mutateAsync(true);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/u-cur\/mcp-install$/);
    expect((init as RequestInit).method).toBe("POST");
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["agents", "u-cur", "mcp-install"],
    });
  });

  test("DELETEs to uninstall when given false", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { installed: false, command: null }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgentMcpInstall("u-cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await result.current.mutateAsync(false);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/u-cur\/mcp-install$/);
    expect((init as RequestInit).method).toBe("DELETE");
  });
});
