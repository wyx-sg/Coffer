// frontend/src/lib/hooks/useMachines.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useMachines, useMachineSlice } from "./useMachines";
import type { MachineSlice } from "./useMachines";
import type { SyncMachine } from "./useSync";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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

const MACHINE: SyncMachine = {
  machine_id: "M-LOCAL",
  display_name: "studio",
  platform: "darwin",
  os_version: "15.0",
  coffer_version: "0.9.0",
  last_sync_at: null,
  is_local: true,
};

describe("useMachines", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("fetches GET /machines and returns the machine list", async () => {
    const fetchMock = stubFetch({ machines: [MACHINE] });

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMachines(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.machines).toEqual([MACHINE]);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/machines$/);
  });

  test("surfaces an ApiError when the request fails", async () => {
    stubFetch({ error: { code: "INTERNAL_ERROR", message: "boom" } }, false, 500);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMachines(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("boom");
  });
});

describe("useMachineSlice", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("fetches GET /machines/{id}/slice and returns the slice", async () => {
    const slice: MachineSlice = {
      machine: MACHINE,
      agents: [{ name: "main", active: true }],
      mcp_servers: [{ name: "fs", active: true, agents: ["main"] }],
      skills: [{ name: "review", active: false, agents: [] }],
      channels: [{ name: "tg", active: true }],
    };
    const fetchMock = stubFetch(slice);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMachineSlice("M-LOCAL"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(slice);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/machines\/M-LOCAL\/slice$/);
  });

  test("is disabled for an empty id", () => {
    const fetchMock = stubFetch({});
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMachineSlice(""), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
