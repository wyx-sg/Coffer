// frontend/src/lib/hooks/useAgentConfig.test.tsx
//
// Covers the spec-004-v2 agent config-file + Coffer-MCP-install hooks that the
// AgentDetailPage drives. Like useAgents.test.tsx these call raw `fetch`
// against `${getCofferBaseUrl()}/agents/*`, so we stub `globalThis.fetch` and
// assert URL shaping, method, body, gating, and cache invalidation.

import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import {
  useAgent,
  usePatchAgent,
  useAgentConfigFiles,
  useAgentConfigFile,
  useSaveAgentConfigFile,
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
  test("GETs the named agent and is gated on a non-empty name", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        name: "cur",
        type: "codex",
        config_dir: "/home/u/.codex",
        description: null,
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    // Empty name → query disabled, no fetch.
    const disabled = renderHook(() => useAgent(""), { wrapper: wrapperFor(makeClient()) });
    expect(disabled.result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();

    const { result } = renderHook(() => useAgent("cur"), { wrapper: wrapperFor(makeClient()) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe("cur");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/cur$/);
  });
});

describe("usePatchAgent", () => {
  test("PATCHes the named agent with the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
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
    await result.current.mutateAsync({ name: "cur", body: { config_dir: "/new/dir" } });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur$/);
    expect((init as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ config_dir: "/new/dir" });
  });
});

describe("useAgentConfigFiles", () => {
  test("GETs the config-files list and is gated on a name", async () => {
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

    const { result } = renderHook(() => useAgentConfigFiles("cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].key).toBe("settings");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/cur\/config-files$/);
  });
});

describe("useAgentConfigFile", () => {
  test("GETs one config file and stays idle until both name and key are present", async () => {
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
    const off = renderHook(() => useAgentConfigFile("cur", null), {
      wrapper: wrapperFor(makeClient()),
    });
    expect(off.result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();

    const { result } = renderHook(() => useAgentConfigFile("cur", "settings"), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.content).toBe("{}");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/cur\/config-files\/settings$/);
  });
});

describe("useSaveAgentConfigFile", () => {
  test("PUTs the new content and invalidates both the file and list queries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        key: "settings",
        display_name: "settings.json",
        path: "/home/u/.codex/settings.json",
        format: "json",
        exists: true,
        size: 20,
        modified_at: "2026-05-23T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const qc = makeClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useSaveAgentConfigFile("cur"), {
      wrapper: wrapperFor(qc),
    });
    await result.current.mutateAsync({ key: "settings", content: '{"a":1}' });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur\/config-files\/settings$/);
    expect((init as RequestInit).method).toBe("PUT");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ content: '{"a":1}' });

    // Both the per-file content query and the metadata list query are refreshed.
    const invalidated = invalidateSpy.mock.calls.map((c) =>
      JSON.stringify((c[0] as { queryKey: unknown }).queryKey),
    );
    expect(invalidated).toContain(JSON.stringify(["agents", "cur", "config-files", "settings"]));
    expect(invalidated).toContain(JSON.stringify(["agents", "cur", "config-files"]));
  });
});

describe("useAgentMcpStatus", () => {
  test("GETs the mcp-install status and is gated on a name", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { installed: false, command: null }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const off = renderHook(() => useAgentMcpStatus(""), { wrapper: wrapperFor(makeClient()) });
    expect(off.result.current.fetchStatus).toBe("idle");

    const { result } = renderHook(() => useAgentMcpStatus("cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.installed).toBe(false);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/cur\/mcp-install$/);
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
    const { result } = renderHook(() => useAgentMcpInstall("cur"), { wrapper: wrapperFor(qc) });
    await result.current.mutateAsync(true);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur\/mcp-install$/);
    expect((init as RequestInit).method).toBe("POST");
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["agents", "cur", "mcp-install"],
    });
  });

  test("DELETEs to uninstall when given false", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { installed: false, command: null }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgentMcpInstall("cur"), {
      wrapper: wrapperFor(makeClient()),
    });
    await result.current.mutateAsync(false);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur\/mcp-install$/);
    expect((init as RequestInit).method).toBe("DELETE");
  });
});
