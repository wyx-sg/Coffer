// src/lib/hooks/useAllAgentSessions.ts — the Conversations list and its row
// writes (spec agent-registry "List every agent's sessions in one list", chat
// "Rename and delete a conversation through its agent"). The list is a first
// page of 30, then 50 more as the reader scrolls, read again when the window
// regains focus and every half minute while the page is visible; a filter or a
// search starts the pages over. A row that has a session is renamed and deleted
// through its agent's session API, a channel conversation no turn has run on
// through the chat conversation API.
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import {
  agentSessionsApi,
  type AgentSessionRow,
  type AllAgentSessionsPage,
} from "@/lib/api/agentSessions";
import { chatApi } from "@/lib/api/chat";
import { translateApiError } from "@/lib/api/errors";
import { agentsKey, allAgentSessionPagesKey, allAgentSessionsKey } from "@/lib/api/queryKeys";
import { useAgents } from "@/lib/hooks/useAgents";
import {
  FIRST_PAGE,
  MORE_PAGE,
  useInfiniteList,
  type InfiniteList,
  type ListPage,
} from "@/lib/hooks/useInfiniteList";
import type { SessionRowData } from "@/lib/sessions/rows";

// Sessions are not on the daemon's change feed, so the list re-reads itself while the page is visible.
// The daemon serves listings from a short in-memory snapshot, and a poll may start one background
// refresh of an agent, so the tick is slow: 30s keeps the list current without loading the machine.
const REFRESH_MS = 30_000;
/** How long a prefetched first page counts as fresh, so repeated hovers do not re-read it. */
const PREFETCH_STALE_MS = 30_000;
const NONE: readonly string[] = [];

/** @ui-only An agent whose sessions could not be read. */
export type UnavailableAgent = AllAgentSessionsPage["unavailable"][number];

interface Args {
  /** The search text, already debounced; "" lists everything. */
  q: string;
  /** `local` and channel uids the server narrows to; empty is every source. */
  source?: readonly string[];
  /** Agent keys; empty is every agent. */
  agent?: readonly string[];
}

/** Reads one page of the cross-agent list; the one fetch the hook and the prefetch share. */
function fetchAllSessionsPage(
  { q, source = NONE, agent = NONE }: Args,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<ListPage<AgentSessionRow, UnavailableAgent[]>> {
  return agentSessionsApi
    .listAll({ q, source, agent, limit: cursor ? MORE_PAGE : FIRST_PAGE, cursor }, signal)
    .then((out) => ({ items: out.sessions, next: out.next_cursor, extra: out.unavailable }));
}

/**
 * Warm the default (unfiltered) view's first page — called when the reader
 * shows intent to open Conversations (hover or focus on its sidebar entry).
 * Same key and fetch as `useAllAgentSessions({ q: "" })`, so the page opens on
 * data already in the cache.
 */
export function prefetchAllAgentSessions(qc: QueryClient): Promise<void> {
  return qc.prefetchInfiniteQuery({
    queryKey: allAgentSessionPagesKey("", { source: NONE, agent: NONE }),
    queryFn: ({ pageParam, signal }) => fetchAllSessionsPage({ q: "" }, pageParam, signal),
    initialPageParam: null as string | null,
    staleTime: PREFETCH_STALE_MS,
  });
}

export function useAllAgentSessions(args: Args): InfiniteList<AgentSessionRow, UnavailableAgent[]> {
  const { q, source = NONE, agent = NONE } = args;
  return useInfiniteList<AgentSessionRow, UnavailableAgent[]>({
    queryKey: allAgentSessionPagesKey(q, { source, agent }),
    fetchPage: (cursor, signal) => fetchAllSessionsPage({ q, source, agent }, cursor, signal),
    refetchInterval: REFRESH_MS,
    refetchOnFocus: true,
    keepPrevious: false,
  });
}

/** The writes on a list row, routed by what the row has. */
export function useSessionRowActions() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const { data: agents = [] } = useAgents();
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: allAgentSessionsKey }),
      qc.invalidateQueries({ queryKey: agentsKey }),
    ]);
  /** The agent registry's uid for the row's agent key. */
  const uidOf = (row: SessionRowData) => agents.find((a) => a.type === row.agentKey)?.uid;

  const rename = useMutation({
    mutationFn: async (vars: { row: SessionRowData; title: string }): Promise<void> => {
      const { row, title } = vars;
      const uid = uidOf(row);
      if (row.sessionId && uid) return agentSessionsApi.rename(uid, row.sessionId, title);
      if (row.conversationId) await chatApi.renameConversation(row.conversationId, title);
    },
    // Returned, so the row's editor stays until the list shows the new title.
    onSuccess: () => refresh(),
    onError: (error) => toast.error(translateApiError(t, error)),
  });

  // No onError toast: the confirmation dialog stays open and shows the refusal.
  const remove = useMutation({
    mutationFn: async (row: SessionRowData): Promise<void> => {
      const uid = uidOf(row);
      if (row.sessionId && uid) return agentSessionsApi.remove(uid, row.sessionId);
      if (row.conversationId) return chatApi.deleteConversation(row.conversationId);
    },
    onSuccess: () => refresh(),
  });

  return { rename, remove };
}
