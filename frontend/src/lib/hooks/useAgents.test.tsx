// frontend/src/lib/hooks/useAgents.test.tsx
//
// TanStack Query bindings for /agents. The `agentsApi` goes through the typed client, which calls fetch
// against `${getCofferBaseUrl()}/agents/*`, so we stub `globalThis.fetch`
// and the typed client reads it afresh for each test (see `resetApiClient`).
//
// Every route below is addressed by the agent's `uid`, never by its name, so
// the fixtures carry both and deliberately disagree: the uid is `u-cur` and
// the label is `cur`. A fixture whose uid spelled its name would let a hook
// that still built its URL from the name pass this file unchanged.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { resetApiClient } from "@/lib/api/client";
import type { PropsWithChildren } from "react";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import {
  useAdoptMcpEntry,
  useAdoptUnmanagedSkill,
  useAgent,
  useAgentTypes,
  useAgentConfigFile,
  useAgentConfigFiles,
  useAgentMcpEntries,
  useAgentConnect,
  useAgentConnection,
  useAgents,
  useDeleteUnmanagedSkill,
  usePatchAgent,
  useRegisterAgent,
  useRemoveAgent,
  useRemoveMcpEntry,
  useTogglePlugin,
  useUninstallPlugin,
} from "./useAgents";

// The typed client keeps the `fetch` it was built with; each test stubs its own.
beforeEach(() => resetApiClient());

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
            uid: "u-cur",
            name: "codex",
            type: "codex",
            config_dir: "/home/u/.codex",
            display_name: "OpenAI Codex",
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
    expect(result.current.data?.[0].name).toBe("codex");
    const calledUrl = (fetchMock.mock.calls[0][0] as Request).url;
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
        uid: "u-cur",
        name: "codex",
        type: "codex",
        config_dir: "/home/u/.codex",
        display_name: "OpenAI Codex",
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
      config_dir: "/home/u/.codex",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents$/);
    expect(request.method).toBe("POST");
  });
});

describe("useRemoveAgent", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("DELETEs the agent the uid names", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useRemoveAgent(), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync("u-cur");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-cur$/);
    expect(request.method).toBe("DELETE");
  });
});

describe("useAgent", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs the agent the uid names", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        uid: "u-cur",
        name: "codex",
        type: "codex",
        config_dir: "/home/u/.codex",
        display_name: "OpenAI Codex",
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgent("u-cur"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // The request went to the uid; what came back is read by its name.
    expect(result.current.data?.name).toBe("codex");
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(/\/agents\/u-cur$/);
  });

  test("does not fetch when the uid is empty", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useAgent(""), { wrapper: wrapper() });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("usePatchAgent", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("PATCHes the agent the uid names with the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        uid: "u-cur",
        name: "codex",
        display_name: "OpenAI Codex",
        type: "codex",
        config_dir: "/home/u/.codex2",
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => usePatchAgent(), { wrapper: wrapper() });
    await result.current.mutateAsync({ uid: "u-cur", body: { config_dir: "/home/u/.codex2" } });
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-cur$/);
    expect(request.method).toBe("PATCH");
    expect(await request.clone().json()).toEqual({
      config_dir: "/home/u/.codex2",
    });
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
    const { result } = renderHook(() => useAgentConfigFiles("u-cur"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].key).toBe("settings.json");
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(/\/agents\/u-cur\/config-files$/);
  });

  test("GETs a single config file when a key is selected, not before", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { key: "settings.json", content: "{}" }));
    vi.stubGlobal("fetch", fetchMock);

    const { result, rerender } = renderHook(
      ({ key }: { key: string | null }) => useAgentConfigFile("u-cur", key),
      { wrapper: wrapper(), initialProps: { key: null as string | null } },
    );
    expect(fetchMock).not.toHaveBeenCalled();

    rerender({ key: "settings.json" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(
      /\/agents\/u-cur\/config-files\/settings.json$/,
    );
  });
});

describe("useAgentConnection / useAgentConnect", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs the Coffer connection", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { state: "connected", parts: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentConnection("u-cur"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-cur\/coffer-connection$/);
    expect(request.method).toBe("GET");
  });

  test("POSTs to connect and DELETEs to disconnect", async () => {
    // A fresh Response per call: a body can only be read once, and the shared
    // `call` reads every 2xx body (it does not swallow a second read).
    const fetchMock = vi
      .fn()
      .mockImplementation(() => jsonResponse(200, { state: "connected", parts: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentConnect("u-cur"), { wrapper: wrapper() });

    await result.current.mutateAsync(true);
    expect((fetchMock.mock.calls[0][0] as Request).method).toBe("POST");

    await result.current.mutateAsync(false);
    expect((fetchMock.mock.calls[1][0] as Request).method).toBe("DELETE");
    expect((fetchMock.mock.calls[1][0] as Request).url).toMatch(
      /\/agents\/u-cur\/coffer-connection$/,
    );
  });
});

describe("useAgentTypes", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs /agents/types and returns the rows", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { types: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentTypes(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(/\/agents\/types$/);
  });
});

describe("useAgentMcpEntries", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("GETs /agents/:uid/mcp-entries and caches under the correct key", async () => {
    const payload = { items: [], parse_errors: [] };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, payload));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentMcpEntries("u-my-agent"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(payload);
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-my-agent\/mcp-entries$/);
    expect(request.method).toBe("GET");
  });
});

describe("useAdoptMcpEntry", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("on success, invalidates mcp-entries and mcp_server resources", async () => {
    // Stub fetch: first call is the mutation POST, then any re-fetch for mcp-entries
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(200, { uid: "u-my-server", kind: "mcp_server", name: "my-server" }),
      )
      // Subsequent re-fetches return empty lists (from invalidation)
      .mockResolvedValue(jsonResponse(200, { items: [], parse_errors: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAdoptMcpEntry("u-my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({ entry: "my-server", body: {} });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-my-agent\/mcp-entries\/my-server\/adopt$/);
    expect(request.method).toBe("POST");
  });
});

describe("useTogglePlugin", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("on success, invalidates plugins query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTogglePlugin("u-my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({ id: "plugin-1", enabled: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-my-agent\/plugins\/plugin-1$/);
    expect(request.method).toBe("PATCH");
    expect(await request.clone().json()).toEqual({ enabled: true });
  });
});

describe("useUninstallPlugin", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("issues a DELETE for the plugin id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUninstallPlugin("u-my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({ id: "plugin-1" });
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-my-agent\/plugins\/plugin-1$/);
    expect(request.method).toBe("DELETE");
  });
});

describe("useAdoptUnmanagedSkill", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("on success, invalidates unmanaged-skills and skills list", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { uid: "u-my-skill", name: "my-skill" }))
      .mockResolvedValue(jsonResponse(200, { items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAdoptUnmanagedSkill("u-my-agent"), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({ skill: "my-skill", location: "global" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0][0] as Request;
    const url = request.url;
    expect(String(url)).toMatch(/\/agents\/u-my-agent\/unmanaged-skills\/my-skill\/adopt$/);
    expect(request.method).toBe("POST");
  });
});

describe("mutation failures are never silent", () => {
  afterEach(() => vi.unstubAllGlobals());

  // Renders inside a real ToastProvider so the hook's onError lands as a
  // visible alert, not the no-op fallback.
  function toastWrapper() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    );
  }

  test.each([
    ["useRemoveAgent", () => useRemoveAgent(), "u-cur"],
    ["useAgentConnect", () => useAgentConnect("u-cur"), true],
    ["useUninstallPlugin", () => useUninstallPlugin("u-cur"), { id: "p1" }],
    ["useTogglePlugin", () => useTogglePlugin("u-cur"), { id: "p1", enabled: true }],
    ["useRemoveMcpEntry", () => useRemoveMcpEntry("u-cur"), { entry: "e" }],
    [
      "useDeleteUnmanagedSkill",
      () => useDeleteUnmanagedSkill("u-cur"),
      { skill: "s", location: "l" },
    ],
    [
      "useAdoptUnmanagedSkill",
      () => useAdoptUnmanagedSkill("u-cur"),
      { skill: "s", location: "l" },
    ],
  ])("%s toasts the server message when the request fails", async (_name, useHook, vars) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        // An unknown code, so the toast falls back to the envelope message.
        jsonResponse(500, { error: { code: "TEST_ONLY_FAILURE", message: "shim missing" } }),
      ),
    );
    const { result } = renderHook(() => useHook() as { mutate: (v: unknown) => void }, {
      wrapper: toastWrapper(),
    });
    act(() => result.current.mutate(vars));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/shim missing/i));
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
