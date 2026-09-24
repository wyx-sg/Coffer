// frontend/src/lib/hooks/useMachines.test.tsx
//
// The machine registry lives behind the sync routes, which answer 404 while
// `vault_sync` is switched off. A channel is still bound to a machine then, so
// the registry reads as empty (what a vault that never converged has) and this
// machine's id comes from the daemon status instead.
import { describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useMachines, useThisMachineId } from "./useMachines";

const machinesApi = vi.fn();
vi.mock("@/lib/api/sync", () => ({ syncApi: { machines: () => machinesApi() } }));

let status: { machine_id: string | null; features: Record<string, boolean> } | undefined;
let statusFailed = false;
vi.mock("@/lib/hooks/useDaemon", () => ({
  useDaemonStatus: () => ({
    data: status,
    isPending: status === undefined && !statusFailed,
    isError: statusFailed,
  }),
}));

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useMachines", () => {
  test("reads the registry while sync is switched on", async () => {
    status = { machine_id: "here", features: { vault_sync: true } };
    machinesApi.mockResolvedValue({ machines: [{ machine_id: "here" }] });
    const { result } = renderHook(() => useMachines(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.machines).toHaveLength(1);
  });

  test("answers an empty registry without asking while sync is switched off", async () => {
    machinesApi.mockClear();
    status = { machine_id: "here", features: { vault_sync: false } };
    const { result } = renderHook(() => useMachines(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.machines).toEqual([]);
    expect(machinesApi).not.toHaveBeenCalled();
  });

  test("answers an empty registry, not a loading one, once the status read has failed", async () => {
    machinesApi.mockClear();
    status = undefined;
    statusFailed = true;
    try {
      const { result } = renderHook(() => useMachines(), { wrapper });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.machines).toEqual([]);
      expect(machinesApi).not.toHaveBeenCalled();
    } finally {
      statusFailed = false;
    }
  });

  test("takes this machine's id from the daemon status", () => {
    status = { machine_id: "here", features: { vault_sync: false } };
    const { result } = renderHook(() => useThisMachineId(), { wrapper });
    expect(result.current).toEqual({ machineId: "here", isPending: false });
  });
});
