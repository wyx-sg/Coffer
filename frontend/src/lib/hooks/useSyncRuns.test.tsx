// src/lib/hooks/useSyncRuns.test.tsx — the Sync rounds list reads 30, then 50 by cursor, and a refresh re-reads page 1 only.
import { beforeEach, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { SyncRound } from "@/lib/api/sync";
import { invalidateSync } from "@/lib/syncInvalidate";

vi.mock("@/lib/api/sync", () => ({ syncApi: { runs: vi.fn() } }));
const { syncApi } = await import("@/lib/api/sync");
const { useSyncRuns } = await import("./useSync");

const round = (id: number) => ({ id }) as SyncRound;
const range = (from: number, n: number) => Array.from({ length: n }, (_, i) => round(from - i));

beforeEach(() => {
  vi.mocked(syncApi.runs).mockReset();
  vi.mocked(syncApi.runs).mockImplementation(async ({ cursor, limit }) => {
    const top = cursor ? Number(cursor) : 200;
    const rounds = range(top, Math.min(limit, top));
    return { rounds, total: 200, next_cursor: top - limit > 0 ? String(top - limit) : null };
  });
});

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, ...renderHook(() => useSyncRuns(), { wrapper }) };
}

test("the first request is 30 rounds, the next 50 by the cursor the server gave", async () => {
  const { result } = setup();
  await waitFor(() => expect(result.current.items).toHaveLength(30));
  expect(result.current.total).toBe(200);
  expect(vi.mocked(syncApi.runs).mock.calls[0][0]).toEqual({ cursor: null, limit: 30 });
  act(() => result.current.loadMore());
  await waitFor(() => expect(result.current.items).toHaveLength(80));
  expect(vi.mocked(syncApi.runs).mock.calls[1][0]).toEqual({ cursor: "170", limit: 50 });
});

test("a refresh after a round re-reads the first page, not every page loaded", async () => {
  const { result, qc } = setup();
  await waitFor(() => expect(result.current.items).toHaveLength(30));
  act(() => result.current.loadMore());
  await waitFor(() => expect(result.current.items).toHaveLength(80));
  vi.mocked(syncApi.runs).mockClear();
  act(() => invalidateSync(qc));
  await waitFor(() => expect(syncApi.runs).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(result.current.items).toHaveLength(30));
  expect(syncApi.runs).toHaveBeenCalledTimes(1);
});
