// frontend/src/lib/hooks/useAgents.test.tsx
//
// TanStack Query bindings for /agents. The `agentsApi` calls raw fetch
// against `${getCofferBaseUrl()}/agents/*`, so we stub `globalThis.fetch`
// rather than the typed `getApiClient` used elsewhere.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { ApiError } from "@/lib/api/errors";
import {
  useAdoptMcpEntry,
  useAdoptUnmanagedSkill,
  useAgent,
  useAgentCandidates,
  useAgentConfigFile,
  useAgentConfigFiles,
  useAgentMcpEntries,
  useAgentMcpInstall,
  useAgentMcpStatus,
  useAgents,
  usePatchAgent,
  useRegisterAgent,
  useRemoveAgent,
  useSaveAgentConfigFile,
  useTogglePlugin,
  useWriteConfigChild,
} from "./useAgents";

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
            type: "codex",
            config_dir: "/home/u/.codex",
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
        type: "codex",
        config_dir: "/home/u/.codex",
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
      type: "codex",
      name: "cur",
      config_dir: "/home/u/.codex",
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

describe("useAgent", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs the named agent", async () => {
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
    const { result } = renderHook(() => useAgent("cur"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe("cur");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/cur$/);
  });

  test("does not fetch when the name is empty", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useAgent(""), { wrapper: wrapper() });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("usePatchAgent", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("PATCHes the named agent with the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        name: "cur",
        type: "codex",
        config_dir: "/home/u/.codex",
        description: "updated",
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => usePatchAgent(), { wrapper: wrapper() });
    await result.current.mutateAsync({ name: "cur", body: { description: "updated" } });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur$/);
    expect((init as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ description: "updated" });
  });
});

describe("useAgentConfigFiles / useAgentConfigFile", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs the config-file list and unwraps items", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        items: [{ key: "settings.json", path: "/x/settings.json", exists: true, size: 10 }],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentConfigFiles("cur"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].key).toBe("settings.json");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agents\/cur\/config-files$/);
  });

  test("GETs a single config file when a key is selected, not before", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { key: "settings.json", content: "{}" }));
    vi.stubGlobal("fetch", fetchMock);

    const { result, rerender } = renderHook(
      ({ key }: { key: string | null }) => useAgentConfigFile("cur", key),
      { wrapper: wrapper(), initialProps: { key: null as string | null } },
    );
    expect(fetchMock).not.toHaveBeenCalled();

    rerender({ key: "settings.json" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(String(fetchMock.mock.calls[0][0])).toMatch(
      /\/agents\/cur\/config-files\/settings.json$/,
    );
  });
});

describe("useSaveAgentConfigFile", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("PUTs the content to the keyed config file", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(200, { key: "settings.json", path: "/x", exists: true, size: 2 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useSaveAgentConfigFile("cur"), { wrapper: wrapper() });
    await result.current.mutateAsync({ key: "settings.json", content: "{}" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur\/config-files\/settings.json$/);
    expect((init as RequestInit).method).toBe("PUT");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ content: "{}" });
  });
});

describe("useAgentMcpStatus / useAgentMcpInstall", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs the MCP install status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { installed: true }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentMcpStatus("cur"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/cur\/mcp-install$/);
    expect((init as RequestInit).method).toBe("GET");
  });

  test("POSTs to install and DELETEs to uninstall", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { installed: true }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentMcpInstall("cur"), { wrapper: wrapper() });

    await result.current.mutateAsync(true);
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("POST");

    await result.current.mutateAsync(false);
    expect((fetchMock.mock.calls[1][1] as RequestInit).method).toBe("DELETE");
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/agents\/cur\/mcp-install$/);
  });
});

describe("useAgentCandidates", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs /agents/candidates when enabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { candidates: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentCandidates(true), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/candidates$/);
    expect((init as RequestInit).method).toBe("GET");
  });

  test("does not fetch while disabled (dialog closed)", () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { candidates: [] }));
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useAgentCandidates(false), { wrapper: wrapper() });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useAgentMcpEntries", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs /agents/:name/mcp-entries and caches under the correct key", async () => {
    const payload = { items: [], parse_errors: [] };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, payload));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentMcpEntries("my-agent"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(payload);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/my-agent\/mcp-entries$/);
    expect((init as RequestInit).method).toBe("GET");
  });
});

describe("useAdoptMcpEntry", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("on success, invalidates mcp-entries and mcp_server resources", async () => {
    // Stub fetch: first call is the mutation POST, then any re-fetch for mcp-entries
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { kind: "mcp_server", name: "my-server" }))
      // Subsequent re-fetches return empty lists (from invalidation)
      .mockResolvedValue(jsonResponse(200, { items: [], parse_errors: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAdoptMcpEntry("my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({ entry: "my-server", body: {} });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/my-agent\/mcp-entries\/my-server\/adopt$/);
    expect((init as RequestInit).method).toBe("POST");
  });
});

describe("useTogglePlugin", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("on success, invalidates plugins query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTogglePlugin("my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({ id: "plugin-1", enabled: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/my-agent\/plugins\/plugin-1$/);
    expect((init as RequestInit).method).toBe("PATCH");
  });
});

describe("useAdoptUnmanagedSkill", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("on success, invalidates unmanaged-skills and skills list", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { name: "my-skill" }))
      .mockResolvedValue(jsonResponse(200, { items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAdoptUnmanagedSkill("my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({ skill: "my-skill", location: "global" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/my-agent\/unmanaged-skills\/my-skill\/adopt$/);
    expect((init as RequestInit).method).toBe("POST");
  });
});

describe("useWriteConfigChild", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("on success, invalidates config-files keys", async () => {
    const responsePayload = {
      key: "settings",
      display_name: "Settings",
      path: "/home/u/.config/settings.json",
      format: "json",
      exists: true,
      size: 42,
      modified_at: "2026-05-22T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, responsePayload));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useWriteConfigChild("my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({
      key: "settings",
      relpath: "foo/bar.json",
      content: '{"x": 1}',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/my-agent\/config-files\/settings\/files\/foo\/bar\.json$/);
    expect((init as RequestInit).method).toBe("PUT");
  });
});

describe("ApiError carries details", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("ApiError.details is populated from a 409 conflict envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, {
          error: {
            code: "CONFLICT",
            message: "already exists",
            details: { suggested_name: "foo-2" },
          },
        }),
      ),
    );
    const { result } = renderHook(() => useAgents(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("CONFLICT");
    expect((err.details as { suggested_name: string }).suggested_name).toBe("foo-2");
  });
});
