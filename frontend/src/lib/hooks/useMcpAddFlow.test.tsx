// frontend/src/lib/hooks/useMcpAddFlow.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { agentMcpEntriesKey, resourcesKey } from "@/lib/api/queryKeys";
import { mockApiClient } from "@/test/mockApiClient";
import {
  useApplyMcpImport,
  useBuiltinMcpServer,
  useMcpConfigTest,
  useMcpImportPlan,
} from "./useMcpAddFlow";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { wrapper, invalidate };
}

function useClient(methods: Record<string, ReturnType<typeof vi.fn>>) {
  getApiClientMock.mockReturnValue(
    mockApiClient(methods) as unknown as ReturnType<typeof getApiClient>,
  );
}

describe("useMcpAddFlow", () => {
  beforeEach(() => vi.clearAllMocks());

  test("a config test posts the config and resolves a failed test as data", async () => {
    const result = { ok: false, latency_ms: 1800, error_code: "exited", exit_code: 1 };
    const POST = vi.fn().mockResolvedValue({ data: result, error: undefined });
    useClient({ POST });
    const { wrapper } = setup();
    const { result: hook } = renderHook(() => useMcpConfigTest(), { wrapper });
    const body = { transport: { type: "stdio" as const, command: "uvx" } };
    let out: unknown;
    await act(async () => {
      out = await hook.current.mutateAsync(body);
    });
    expect(out).toEqual(result);
    expect(POST).toHaveBeenCalledWith(
      "/resources/mcp_server/test-config",
      expect.objectContaining({ body, signal: expect.any(AbortSignal) }),
    );
  });

  test("cancel aborts the running test", async () => {
    let signal: AbortSignal | undefined;
    const POST = vi.fn().mockImplementation((_p, init: { signal: AbortSignal }) => {
      signal = init.signal;
      return new Promise(() => {});
    });
    useClient({ POST });
    const { wrapper } = setup();
    const { result: hook } = renderHook(() => useMcpConfigTest(), { wrapper });
    act(() => hook.current.mutate({ transport: { type: "stdio", command: "x" } }));
    await waitFor(() => expect(signal).toBeDefined());
    act(() => hook.current.cancel());
    expect(signal?.aborted).toBe(true);
  });

  test("a config test that the daemon refuses rejects with its message", async () => {
    const POST = vi.fn().mockResolvedValue({
      data: undefined,
      error: { error: { code: "VALIDATION_ERROR", message: "bad config" } },
    });
    useClient({ POST });
    const { wrapper } = setup();
    const { result: hook } = renderHook(() => useMcpConfigTest(), { wrapper });
    await act(async () => {
      await expect(
        hook.current.mutateAsync({ transport: { type: "stdio", command: "x" } }),
      ).rejects.toThrow("bad config");
    });
  });

  test("the import plan is read for the chosen entries only when there are some", async () => {
    const plan = { servers: [], files: [], agents: [], unavailable: [], changes: [] };
    const POST = vi.fn().mockResolvedValue({ data: plan, error: undefined });
    useClient({ POST });
    const { wrapper } = setup();
    const entries = [{ agent_uid: "u1", name: "github", source: "global" }];
    const { result } = renderHook(() => useMcpImportPlan(entries), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(plan);
    expect(POST).toHaveBeenCalledWith("/agents/mcp-import/plan", { body: { entries } });

    POST.mockClear();
    renderHook(() => useMcpImportPlan([]), { wrapper });
    expect(POST).not.toHaveBeenCalled();
  });

  test("applying an import refreshes each agent's entries and the resource lists", async () => {
    const report = { entries: [], servers_added: [], coffer_entry_results: [] };
    const POST = vi.fn().mockResolvedValue({ data: report, error: undefined });
    useClient({ POST });
    const { wrapper, invalidate } = setup();
    const { result } = renderHook(() => useApplyMcpImport(), { wrapper });
    const entries = [
      { agent_uid: "u1", name: "a" },
      { agent_uid: "u2", name: "b" },
      { agent_uid: "u1", name: "c" },
    ];
    await act(async () => {
      await result.current.mutateAsync(entries);
    });
    expect(POST).toHaveBeenCalledWith("/agents/mcp-import/apply", { body: { entries } });
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(agentMcpEntriesKey("u1")));
    expect(keys).toContain(JSON.stringify(agentMcpEntriesKey("u2")));
    expect(keys).toContain(JSON.stringify(resourcesKey));
    expect(keys.filter((k) => k === JSON.stringify(agentMcpEntriesKey("u1")))).toHaveLength(1);
  });

  test("the built-in server is read from /mcp/builtin", async () => {
    const builtin = { name: "coffer", url: "http://127.0.0.1:8000/mcp", tools: [] };
    const GET = vi.fn().mockResolvedValue({ data: builtin, error: undefined });
    useClient({ GET });
    const { wrapper } = setup();
    const { result } = renderHook(() => useBuiltinMcpServer(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(GET).toHaveBeenCalledWith("/mcp/builtin");
    expect(result.current.data?.name).toBe("coffer");
  });
});
