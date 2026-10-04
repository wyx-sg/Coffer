// src/lib/hooks/useConversationList.ts — the Conversations list: a first page of 30, then 50 more as the reader scrolls (spec chat "List conversations by latest activity").
//
// The pages are read once and again when the window regains focus and every few
// seconds while the page is visible, so a channel's new conversation and the
// Running / Needs you marks keep up without a reload; a filter or a search
// starts the pages over.
import { chatApi, type Conversation } from "@/lib/api/chat";
import { conversationPagesKey } from "@/lib/api/queryKeys";
import {
  FIRST_PAGE,
  MORE_PAGE,
  useInfiniteList,
  type InfiniteList,
} from "@/lib/hooks/useInfiniteList";

// Conversations are not on the daemon's change feed (they are not resources),
// so the list re-reads itself while the page is visible.
const REFRESH_MS = 10_000;
const NONE: readonly string[] = [];

interface Args {
  /** The search text, already debounced; "" lists everything. */
  q: string;
  /** Channel uids and agent keys the server narrows to; empty is every one. */
  source?: readonly string[];
  agent?: readonly string[];
  enabled?: boolean;
}

export function useConversationList({
  q,
  source = NONE,
  agent = NONE,
  enabled = true,
}: Args): InfiniteList<Conversation> {
  return useInfiniteList<Conversation>({
    queryKey: conversationPagesKey(q, { source, agent }),
    fetchPage: async (cursor, signal) => {
      const out = await chatApi.listConversations(
        { q, source, agent, limit: cursor ? MORE_PAGE : FIRST_PAGE, cursor },
        signal,
      );
      return { items: out.conversations, next: out.next_cursor, total: out.total };
    },
    enabled,
    refetchInterval: REFRESH_MS,
    refetchOnFocus: true,
    keepPrevious: false,
  });
}
