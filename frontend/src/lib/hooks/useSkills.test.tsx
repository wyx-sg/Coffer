// frontend/src/lib/hooks/useSkills.test.tsx — TEST21-013
//
// TanStack Query bindings for /skills. We stub `globalThis.fetch` directly
// because `skillsApi.*` is plain fetch (no abstracted API client).

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import {
  useSkills,
  useImportSkill,
  useFetchSkill,
  useEnableSkill,
  useDisableSkill,
  useRemoveSkill,
  useVerifySkills,
} from "./useSkills";

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

const SAMPLE_SKILL = {
  name: "hello",
  description: "test",
  source: { type: "local_import", original_path: "/tmp/hello" },
  enabled: true,
  version_hash: "abc",
  master_path: "/tmp/master/hello",
  last_synced_from_source_at: null,
  created_at: "2026-05-26T00:00:00Z",
  updated_at: "2026-05-26T00:00:00Z",
  bindings: [],
};

describe("useSkills", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  test("returns the items array on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [SAMPLE_SKILL] }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useSkills(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("hello");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/skills$/);
  });

  test("throws on a non-2xx envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(500, { error: { code: "BOOM", message: "kaboom" } })),
    );
    const { result } = renderHook(() => useSkills(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("kaboom");
  });
});

describe("useImportSkill", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("POSTs the path and invalidates the skills query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, SAMPLE_SKILL));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useImportSkill(), { wrapper: wrapper() });
    await result.current.mutateAsync({ path: "/tmp/hello" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/skills\/import$/);
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      path: "/tmp/hello",
    });
  });
});

describe("useFetchSkill", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("POSTs the git URL body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, SAMPLE_SKILL));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useFetchSkill(), { wrapper: wrapper() });
    await result.current.mutateAsync({
      git_url: "https://example.com/repo",
      git_ref: "main",
      git_subpath: "",
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/skills\/fetch$/);
    expect((init as RequestInit).method).toBe("POST");
  });
});

describe("useEnableSkill", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("POSTs to /skills/{name}/enable with the agent body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        agent_name: "cur",
        enabled: true,
        last_linked_at: null,
        last_link_path: null,
        link_mode: "symlink",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useEnableSkill(), { wrapper: wrapper() });
    await result.current.mutateAsync({
      name: "hello",
      body: { agent_name: "cur" },
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/skills\/hello\/enable$/);
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      agent_name: "cur",
    });
  });
});

describe("useDisableSkill", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("POSTs to /skills/{name}/disable", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        agent_name: "cur",
        enabled: false,
        last_linked_at: null,
        last_link_path: null,
        link_mode: null,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useDisableSkill(), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync({
      name: "hello",
      body: { agent_name: "cur" },
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/skills\/hello\/disable$/);
    expect((init as RequestInit).method).toBe("POST");
  });
});

describe("useRemoveSkill", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("DELETEs the named skill", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useRemoveSkill(), {
      wrapper: wrapper(),
    });
    await result.current.mutateAsync("hello");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/skills\/hello$/);
    expect((init as RequestInit).method).toBe("DELETE");
  });
});

describe("useVerifySkills", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("POSTs /skills/verify and returns the drift report", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { entries: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useVerifySkills(), {
      wrapper: wrapper(),
    });
    const report = await result.current.mutateAsync();
    expect(report.entries).toEqual([]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/skills\/verify$/);
    expect((init as RequestInit).method).toBe("POST");
  });
});
