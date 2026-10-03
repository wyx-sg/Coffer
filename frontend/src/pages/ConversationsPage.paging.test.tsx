// pages/ConversationsPage.paging.test.tsx — the list reads 30 and then 50 as it is scrolled, and its search and filters ask the server rather than the loaded rows.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ConversationsPage } from "./ConversationsPage";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeConversation } from "@/test/conversationFixtures";
import { makeBinding } from "@/test/conversationFixtures";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/chat", () => ({ chatApi: { listConversations: vi.fn() } }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: {
    list: vi.fn().mockResolvedValue({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
    }),
  },
}));
vi.mock("@/lib/hooks/useChannels", () => ({ useChannels: () => ({ data: [] }) }));
vi.mock("@/lib/chat/streamClient", () => ({
  subscribeConversationEvents: vi.fn(async function* () {}),
}));

const { chatApi } = await import("@/lib/api/chat");
const list = chatApi.listConversations as unknown as ReturnType<typeof vi.fn>;

const rows = (prefix: string, n: number, extra = {}) =>
  Array.from({ length: n }, (_, i) =>
    makeConversation({ id: `${prefix}${i}`, title: `${prefix} ${i}`, ...extra }),
  );

let observers: IntersectionObserverCallback[] = [];
beforeEach(() => {
  vi.clearAllMocks();
  observers = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: IntersectionObserverCallback) {
        observers.push(cb);
      }
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function renderPage(path = "/conversations") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page = <ConversationsPage />;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <TooltipProvider>
            <Routes>
              <Route path="/conversations" element={page} />
              <Route path="/conversations/:id" element={page} />
            </Routes>
          </TooltipProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const intersect = () =>
  act(() =>
    observers.at(-1)?.(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    ),
  );

describe("ConversationsPage paging", () => {
  test("opens on a page of 30, then the end of the list reads the next 50 from the cursor", async () => {
    list.mockResolvedValueOnce({ conversations: rows("a", 30), next_cursor: "c1" });
    renderPage();
    expect(await screen.findByText("a 0")).toBeInTheDocument();
    expect(list.mock.calls[0][0]).toMatchObject({ limit: 30, archived: false });
    expect(list.mock.calls[0][0].cursor).toBeFalsy();
    expect(screen.getByText("30 loaded")).toBeInTheDocument();

    list.mockResolvedValueOnce({ conversations: rows("b", 5), next_cursor: null });
    intersect();
    expect(await screen.findByText("b 4")).toBeInTheDocument();
    expect(list.mock.calls[1][0]).toMatchObject({ limit: 50, cursor: "c1" });
    expect(list.mock.calls[1][1]).toBeInstanceOf(AbortSignal);
    expect(screen.getByText("35 loaded")).toBeInTheDocument();
  });

  test("Load more is always there for a reader who cannot scroll", async () => {
    list.mockResolvedValueOnce({ conversations: rows("a", 30), next_cursor: "c1" });
    renderPage();
    await screen.findByText("a 0");
    list.mockResolvedValueOnce({ conversations: rows("b", 2), next_cursor: null });
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("b 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  test("the search sends q once typing pauses, from the first page", async () => {
    list.mockImplementation(async (opts: { q?: string }) => ({
      conversations: opts.q ? rows("hit", 1) : rows("a", 3),
      next_cursor: null,
    }));
    renderPage();
    await screen.findByText("a 0");
    const box = screen.getByRole("textbox", { name: "Search titles…" });
    fireEvent.change(box, { target: { value: "dep" } });
    fireEvent.change(box, { target: { value: "deploy" } });
    expect(list).toHaveBeenCalledTimes(1); // nothing asked for per keystroke
    expect(await screen.findByText("hit 0")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
    expect(list.mock.calls[1][0]).toMatchObject({ q: "deploy", limit: 30 });
    expect(list.mock.calls[1][0].cursor).toBeFalsy();
    expect(screen.queryByText("a 0")).not.toBeInTheDocument();
  });

  acceptance("chat", "a search that matches nothing is not an empty list", async () => {
    list.mockImplementation(async (opts: { q?: string }) => ({
      conversations: opts.q ? [] : rows("a", 1),
      next_cursor: null,
    }));
    renderPage();
    await screen.findByText("a 0");
    const box = screen.getByRole("textbox", { name: "Search titles…" });
    fireEvent.change(box, { target: { value: "zzz" } });
    expect(await screen.findByText("No conversations match")).toBeInTheDocument();
    expect(screen.queryByText("No conversations yet")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Search titles…" })).toHaveValue("zzz");
  });

  acceptance("chat", "an empty conversation list offers no search", async () => {
    list.mockResolvedValue({ conversations: [], next_cursor: null });
    renderPage();
    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Search titles…" })).not.toBeInTheDocument();
  });

  test("a filter that empties what is loaded keeps reading while more exist", async () => {
    const tg = makeBinding({ platform: "telegram" });
    list
      .mockResolvedValueOnce({ conversations: rows("a", 30), next_cursor: "c1" })
      .mockResolvedValueOnce({
        conversations: rows("t", 2, { channel_binding: tg }),
        next_cursor: null,
      });
    renderPage("/conversations?source=telegram");
    expect(await screen.findByText("t 1")).toBeInTheDocument();
    expect(screen.queryByText("No conversations match")).not.toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  test("the archived view reads the archived listing", async () => {
    list.mockImplementation(async (opts: { archived?: boolean }) => ({
      conversations: opts.archived ? rows("old", 2, { archived_at: "2026-02-01T00:00:00Z" }) : [],
      next_cursor: null,
    }));
    renderPage("/conversations?archived=1");
    expect(await screen.findByText("old 1")).toBeInTheDocument();
    await waitFor(() =>
      expect(list.mock.calls.some(([o]) => o.archived === true && o.limit === 30)).toBe(true),
    );
  });
});
