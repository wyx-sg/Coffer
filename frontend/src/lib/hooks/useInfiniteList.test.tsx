// src/lib/hooks/useInfiniteList.test.tsx — the shared cursor-paged list hook: small first page, more on demand, a new key starts over.
import { expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { FIRST_PAGE, MORE_PAGE, useInfiniteList, type ListPage } from "./useInfiniteList";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    {children}
  </QueryClientProvider>
);

/** A 120-row list served by cursor. */
function server() {
  return vi.fn(async (cursor: string | null): Promise<ListPage<number>> => {
    const from = cursor ? Number(cursor) : 0;
    const size = cursor ? MORE_PAGE : FIRST_PAGE;
    const items = Array.from({ length: Math.min(size, 120 - from) }, (_, i) => from + i);
    return { items, next: from + size < 120 ? String(from + size) : null, total: 120 };
  });
}

test("it reads one small first page, then the next by the cursor the server gave", async () => {
  const fetchPage = server();
  const { result } = renderHook(() => useInfiniteList({ queryKey: ["t", 1], fetchPage }), {
    wrapper,
  });
  await waitFor(() => expect(result.current.items).toHaveLength(30));
  expect(result.current.total).toBe(120);
  expect(result.current.hasMore).toBe(true);
  expect(fetchPage).toHaveBeenCalledTimes(1);

  act(() => result.current.loadMore());
  await waitFor(() => expect(result.current.items).toHaveLength(80));
  expect(fetchPage.mock.calls[1][0]).toBe("30");
  act(() => result.current.loadMore());
  await waitFor(() => expect(result.current.items).toHaveLength(120));
  expect(result.current.hasMore).toBe(false);
  // At the end, asking again reads nothing.
  act(() => result.current.loadMore());
  expect(fetchPage).toHaveBeenCalledTimes(3);
});

test("a new key starts again from the first page and aborts the request still in flight", async () => {
  let aborted = false;
  const fetchPage = vi.fn(
    (cursor: string | null, signal: AbortSignal): Promise<ListPage<string>> =>
      new Promise((resolve, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(new Error("aborted"));
        });
        if (cursor === null && fetchPage.mock.calls.length > 1)
          resolve({ items: ["b"], next: null });
      }),
  );
  const { result, rerender } = renderHook(
    ({ q }: { q: string }) => useInfiniteList({ queryKey: ["t", q], fetchPage }),
    { wrapper, initialProps: { q: "a" } },
  );
  await waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(1));
  expect(result.current.isLoading).toBe(true);
  rerender({ q: "b" });
  await waitFor(() => expect(result.current.items).toEqual(["b"]));
  expect(aborted).toBe(true);
});
