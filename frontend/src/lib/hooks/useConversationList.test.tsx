// frontend/src/lib/hooks/useConversationList.test.tsx — the list reads 30 and then 50, by title search, and keeps current without re-walking its pages.
import type { PropsWithChildren } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { Conversation } from "@/lib/api/chat";
import { applyHead, useConversationList, useConversationSearch } from "./useConversationList";

const { listConversations } = vi.hoisted(() => ({ listConversations: vi.fn() }));
vi.mock("@/lib/api/chat", () => ({ chatApi: { listConversations } }));

const conv = (id: string, extra: Partial<Conversation> = {}) =>
  ({ id, title: id, running: false, ...extra }) as Conversation;
const page = (ids: string[], next: string | null = null) => ({
  conversations: ids.map((id) => conv(id)),
  next_cursor: next,
});

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrap = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, Wrap };
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.useRealTimers());

describe("useConversationList", () => {
  test("reads a first page of 30, then 50 more from the cursor", async () => {
    listConversations.mockResolvedValueOnce(page(["a", "b"], "c1"));
    const { Wrap } = wrapper();
    const { result } = renderHook(() => useConversationList({ archived: false, q: "" }), {
      wrapper: Wrap,
    });

    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(listConversations.mock.calls[0][0]).toMatchObject({ limit: 30, cursor: null });
    expect(result.current.hasMore).toBe(true);

    listConversations.mockResolvedValueOnce(page(["c"]));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items.map((c) => c.id)).toEqual(["a", "b", "c"]));
    expect(listConversations.mock.calls[1][0]).toMatchObject({ limit: 50, cursor: "c1" });
    expect(listConversations.mock.calls[1][1]).toBeInstanceOf(AbortSignal);
    expect(result.current.hasMore).toBe(false);
  });

  test("a new search starts again from the first page and aborts the one in flight", async () => {
    let firstSignal: AbortSignal | undefined;
    listConversations.mockImplementationOnce(
      (_opts: unknown, signal: AbortSignal) =>
        new Promise((_res, rej) => {
          firstSignal = signal;
          signal.addEventListener("abort", () => rej(new DOMException("x", "AbortError")));
        }),
    );
    listConversations.mockResolvedValue(page(["m"]));
    const { Wrap } = wrapper();
    const { result, rerender } = renderHook(
      ({ q }) => useConversationList({ archived: false, q }),
      { wrapper: Wrap, initialProps: { q: "" } },
    );
    await waitFor(() => expect(listConversations).toHaveBeenCalledTimes(1));

    rerender({ q: "deploy" });
    await waitFor(() => expect(result.current.items.map((c) => c.id)).toEqual(["m"]));
    expect(firstSignal?.aborted).toBe(true);
    expect(listConversations.mock.calls[1][0]).toMatchObject({
      q: "deploy",
      limit: 30,
      cursor: null,
    });
  });

  test("the archived list reads the archived listing", async () => {
    listConversations.mockResolvedValue(page(["old"]));
    const { Wrap } = wrapper();
    const { result } = renderHook(() => useConversationList({ archived: true, q: "" }), {
      wrapper: Wrap,
    });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(listConversations.mock.calls[0][0]).toMatchObject({ archived: true, limit: 30 });
  });

  test("the head poll re-reads one page, never the pages already loaded", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    listConversations.mockResolvedValueOnce(page(["a", "b"], "c1"));
    const { Wrap } = wrapper();
    const { result } = renderHook(() => useConversationList({ archived: false, q: "" }), {
      wrapper: Wrap,
    });
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    listConversations.mockResolvedValueOnce(page(["c"]));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(3));
    expect(listConversations).toHaveBeenCalledTimes(2);

    // A new conversation and a running mark arrive on the head.
    listConversations.mockResolvedValueOnce({
      conversations: [conv("new"), conv("a", { running: true })],
      next_cursor: null,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_500);
    });
    await waitFor(() =>
      expect(result.current.items.map((c) => c.id)).toEqual(["new", "a", "b", "c"]),
    );
    expect(result.current.items[1].running).toBe(true);
    // Exactly one more request, for the head (30 rows), not for every loaded page.
    expect(listConversations).toHaveBeenCalledTimes(3);
    expect(listConversations.mock.calls[2][0]).toMatchObject({ limit: 30 });
    expect(listConversations.mock.calls[2][0].cursor).toBeUndefined();
  });
});

describe("applyHead", () => {
  const data = (...pages: string[][]) => ({
    pages: pages.map((ids) => ({ items: ids.map((id) => conv(id)), next: null })),
    pageParams: pages.map(() => null),
  });

  test("scrolled down it updates rows in place and leaves new ones out", () => {
    const out = applyHead(data(["a", "b"]), [conv("new"), conv("b", { running: true })], false);
    expect(out.pages[0].items.map((c) => c.id)).toEqual(["a", "b"]);
    expect(out.pages[0].items[1].running).toBe(true);
  });

  test("at the top the head's rows move to the front, once", () => {
    const out = applyHead(data(["a", "b"], ["c"]), [conv("c"), conv("new")], true);
    expect(out.pages.flatMap((p) => p.items.map((c) => c.id))).toEqual(["c", "new", "a", "b"]);
  });
});

describe("useConversationSearch", () => {
  test("asks for 8 rows by the typed text once typing pauses, and the first page without", async () => {
    listConversations.mockResolvedValue(page(["x"]));
    const { Wrap } = wrapper();
    const { result, rerender } = renderHook(({ t }) => useConversationSearch(t), {
      wrapper: Wrap,
      initialProps: { t: "" },
    });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(listConversations.mock.calls[0][0]).toMatchObject({ limit: 30 });
    expect(listConversations.mock.calls[0][0].q).toBeFalsy();

    rerender({ t: "dep" });
    await waitFor(() => expect(listConversations).toHaveBeenCalledTimes(2));
    expect(listConversations.mock.calls[1][0]).toMatchObject({ q: "dep", limit: 8 });
  });
});
