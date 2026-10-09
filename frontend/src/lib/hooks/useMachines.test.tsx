// frontend/src/lib/hooks/useMachines.test.tsx
//
// The machine registry, and this machine's id — which comes from the daemon
// status rather than the sync routes, so a channel is bound to a machine
// whether or not this vault syncs anywhere.
import { describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useMachines, useThisMachineId } from "./useMachines";

const machinesApi = vi.fn();
vi.mock("@/lib/api/sync", () => ({ syncApi: { machines: () => machinesApi() } }));

let status: { machine_id: string | null; features: Record<string, boolean> } | undefined;
vi.mock("@/lib/hooks/useDaemon", () => ({
  useDaemonStatus: () => ({
    data: status,
    isPending: status === undefined,
    isError: false,
  }),
}));

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useMachines", () => {
  test("reads the registry", async () => {
    status = { machine_id: "here", features: {} };
    machinesApi.mockResolvedValue({ machines: [{ machine_id: "here" }] });
    const { result } = renderHook(() => useMachines(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.machines).toHaveLength(1);
  });

  test("takes this machine's id from the daemon status", () => {
    status = { machine_id: "here", features: {} };
    const { result } = renderHook(() => useThisMachineId(), { wrapper });
    expect(result.current).toEqual({ machineId: "here", isPending: false });
  });
});
