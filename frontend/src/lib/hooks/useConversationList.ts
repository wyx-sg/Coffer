// src/lib/hooks/useConversationList.ts — the Conversations list: a first page of 30, then 50 more as the reader scrolls (spec chat "List conversations by latest activity").
//
// Two reads keep it current without re-walking what was loaded. The **pages**
// are what the list shows, read once (`useInfiniteList`) and again only when a
// change the page itself made invalidates them. The **head** is the newest
// page, re-read every few seconds: its rows replace the loaded copies in place
// (a Running mark, the latest line, a title) and, while the reader is at the
// top of the page, new and bumped conversations move to the head of the list.
// Scrolled down, the list stays put until the reader is back at the top.
import { useEffect, useState } from "react";
import {
  useQuery,
  useQueryClient,
  keepPreviousData,
  type InfiniteData,
} from "@tanstack/react-query";

import { chatApi, type Conversation } from "@/lib/api/chat";
import {
  conversationHeadKey,
  conversationPagesKey,
  paletteConversationsKey,
} from "@/lib/api/queryKeys";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import {
  FIRST_PAGE,
  MORE_PAGE,
  useInfiniteList,
  type InfiniteList,
  type ListPage,
} from "@/lib/hooks/useInfiniteList";

// Conversations are not on the daemon's change feed (they are not resources),
// so the head re-reads itself while the page is visible: a channel's new
// conversation, a Running mark and the latest line keep up without a reload.
const HEAD_REFRESH_MS = 10_000;
/** Rows the command palette asks for while the user is typing. */
const PALETTE_SEARCH_LIMIT = 8;
/** Within this many pixels of the top counts as "at the top". */
const TOP_SLACK = 8;
const NONE: readonly string[] = [];

type Pages = InfiniteData<ListPage<Conversation>, string | null>;

/** Whether the reader is at the top of whatever last scrolled (the page, in practice). */
function useScrolledToTop(): boolean {
  const [top, setTop] = useState(true);
  useEffect(() => {
    // Scroll events do not bubble; capturing sees every scroller on the page.
    const onScroll = (event: Event) => {
      const el = event.target;
      if (el instanceof HTMLElement) setTop(el.scrollTop <= TOP_SLACK);
    };
    document.addEventListener("scroll", onScroll, { capture: true, passive: true });
    return () => document.removeEventListener("scroll", onScroll, true);
  }, []);
  return top;
}

/**
 * The loaded pages with the head's rows applied: a row already loaded takes
 * the head's copy in place; with `atTop`, the head's rows also move to the
 * front (they are the newest of all, so everything else is older).
 */
export function applyHead(data: Pages, head: readonly Conversation[], atTop: boolean): Pages {
  const byId = new Map(head.map((c) => [c.id, c]));
  const pages = data.pages.map((p) => ({ ...p, items: p.items.map((c) => byId.get(c.id) ?? c) }));
  if (atTop && pages.length > 0) {
    const inHead = new Set(byId.keys());
    for (const p of pages) p.items = p.items.filter((c) => !inHead.has(c.id));
    pages[0] = { ...pages[0], items: [...head, ...pages[0].items] };
  }
  return { ...data, pages };
}

interface Args {
  archived: boolean;
  /** The title search, already debounced; "" lists everything. */
  q: string;
  /** Source tokens and agent keys the server narrows to; empty is every one. */
  source?: readonly string[];
  agent?: readonly string[];
  enabled?: boolean;
}

export function useConversationList({
  archived,
  q,
  source = NONE,
  agent = NONE,
  enabled = true,
}: Args): InfiniteList<Conversation> {
  const qc = useQueryClient();
  const pagesKey = conversationPagesKey(archived, q, { source, agent });
  const headKey = conversationHeadKey(archived, q, { source, agent });
  const list = useInfiniteList<Conversation>({
    queryKey: pagesKey,
    fetchPage: async (cursor, signal) => {
      const out = await chatApi.listConversations(
        { archived, q, source, agent, limit: cursor ? MORE_PAGE : FIRST_PAGE, cursor },
        signal,
      );
      // The first page is also the head's first answer: it is not asked for twice.
      if (!cursor) qc.setQueryData(headKey, out);
      return { items: out.conversations, next: out.next_cursor, total: out.total };
    },
    enabled,
    staleTime: Infinity,
    keepPrevious: false,
  });

  const loaded = enabled && !archived && !list.isLoading && !list.error;
  const head = useQuery({
    queryKey: headKey,
    queryFn: ({ signal }) =>
      chatApi.listConversations({ archived, q, source, agent, limit: FIRST_PAGE }, signal),
    enabled: loaded,
    staleTime: HEAD_REFRESH_MS - 1_000,
    refetchInterval: HEAD_REFRESH_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  });
  const atTop = useScrolledToTop();
  const headRows = head.data?.conversations;
  useEffect(() => {
    if (!headRows) return;
    qc.setQueryData<Pages>(pagesKey, (data) => (data ? applyHead(data, headRows, atTop) : data));
  }, [qc, pagesKey, headRows, atTop]);

  return list;
}

/** What the command palette lists: a small read by the text typed (8 rows), the first page without. */
export function useConversationSearch(text: string) {
  const q = useDebouncedValue(text.trim());
  return useQuery({
    queryKey: paletteConversationsKey(q),
    queryFn: async ({ signal }) =>
      (await chatApi.listConversations({ q, limit: q ? PALETTE_SEARCH_LIMIT : FIRST_PAGE }, signal))
        .conversations,
    placeholderData: keepPreviousData,
    staleTime: 5_000,
  });
}
