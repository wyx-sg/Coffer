// src/lib/hooks/useUpkeep.test.ts
//
// The hook that makes the organise / curate buttons survive a navigation: the
// running state comes from the daemon's own list, not from a mutation object
// that dies with the component.
import { describe, expect, test, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/lib/api/upkeep", () => ({ listUpkeepRuns: vi.fn() }));

const { listUpkeepRuns } = await import("@/lib/api/upkeep");
const { useUpkeepRun, useUpkeepRunning } = await import("./useUpkeep");
const listMock = vi.mocked(listUpkeepRuns);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return createElement(QueryClientProvider, { client: qc }, children);
}

function answer(runs: { kind: string; name: string }[]) {
  listMock.mockResolvedValue({
    runs: runs.map((r) => ({ ...r, started_at: "2026-09-16T00:00:00Z" })),
  } as Awaited<ReturnType<typeof listUpkeepRuns>>);
}

describe("useUpkeepRunning", () => {
  beforeEach(() => listMock.mockReset());

  test("is false before the first answer arrives", () => {
    answer([{ kind: "memory", name: "coffer" }]);
    const { result } = renderHook(() => useUpkeepRunning("memory", "coffer"), { wrapper });
    // The page's own optimistic pending state covers this moment; a mount that
    // has not heard back has no grounds to claim a pass is running.
    expect(result.current).toBe(false);
  });

  test("reports a pass this browser never started", async () => {
    // The whole point: the pass was started elsewhere (another tab, the CLI,
    // the interval worker) or before this component mounted.
    answer([{ kind: "memory", name: "coffer" }]);
    const { result } = renderHook(() => useUpkeepRunning("memory", "coffer"), { wrapper });
    await waitFor(() => expect(result.current).toBe(true));
  });

  test("matches on kind as well as name", async () => {
    // A partition and a collection may share a name and are not one target.
    answer([{ kind: "knowledge", name: "coffer" }]);
    const { result } = renderHook(() => useUpkeepRunning("memory", "coffer"), { wrapper });
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });

  test("is false for a target absent from the list", async () => {
    answer([{ kind: "memory", name: "other" }]);
    const { result } = renderHook(() => useUpkeepRunning("memory", "coffer"), { wrapper });
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });
});

describe("useUpkeepRun", () => {
  beforeEach(() => {
    listMock.mockReset();
  });

  test("finds the run by the target's uid and carries its n of m", async () => {
    // The daemon claims a pass under the collection's uid, never its name.
    listMock.mockResolvedValue({
      runs: [
        {
          kind: "knowledge",
          name: "kn-8c1f",
          started_at: "2026-09-30T00:00:00Z",
          done: 1,
          total: 3,
        },
      ],
    });
    const { result } = renderHook(() => useUpkeepRun("knowledge", "kn-8c1f"), { wrapper });
    await waitFor(() => expect(result.current).toMatchObject({ done: 1, total: 3 }));
  });
});
