// frontend/src/lib/hooks/useAgentSessions.ts — an agent's own sessions for its
// Sessions tab (spec agent-registry "List an agent's native sessions through
// the agent", "Rename and delete a native session through the agent"): the
// cursor-paged list and the two writes. A session a channel conversation points
// at is that conversation too, so a write also refreshes the Conversations list.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { agentSessionsApi, type AgentSession } from "@/lib/api/agentSessions";
import { translateApiError } from "@/lib/api/errors";
import { agentSessionsKey, allAgentSessionsKey } from "@/lib/api/queryKeys";
import { FIRST_PAGE, MORE_PAGE, useInfiniteList } from "@/lib/hooks/useInfiniteList";

// Sessions are not on the daemon's change feed: the list re-reads itself while
// the page is visible, so a Running mark keeps up without a reload. The daemon
// serves listings from a short snapshot and a poll may start one background
// refresh of the agent, so the tick is 30s.
const REFRESH_MS = 30_000;

export function useAgentSessions(uid: string, q: string) {
  return useInfiniteList<AgentSession>({
    queryKey: agentSessionsKey(uid, q),
    fetchPage: async (cursor, signal) => {
      const out = await agentSessionsApi.list(
        uid,
        { q, limit: cursor ? MORE_PAGE : FIRST_PAGE, cursor },
        signal,
      );
      // `total` is null where the agent cannot count (Codex).
      return { items: out.sessions, next: out.next_cursor, total: out.total ?? undefined };
    },
    enabled: !!uid,
    refetchInterval: REFRESH_MS,
    refetchOnFocus: true,
    keepPrevious: false,
  });
}

function useRefreshLists(uid: string) {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: agentSessionsKey(uid) }),
      qc.invalidateQueries({ queryKey: allAgentSessionsKey }),
    ]);
}

export function useRenameAgentSession(uid: string) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const refresh = useRefreshLists(uid);
  return useMutation({
    mutationFn: (vars: { sessionId: string; title: string }) =>
      agentSessionsApi.rename(uid, vars.sessionId, vars.title),
    // Returned, so the row's editor stays until the list shows the new title.
    onSuccess: () => refresh(),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDeleteAgentSession(uid: string) {
  const refresh = useRefreshLists(uid);
  // No onError toast: the confirmation dialog stays open and shows the refusal.
  return useMutation({
    mutationFn: (sessionId: string) => agentSessionsApi.remove(uid, sessionId),
    onSuccess: () => refresh(),
  });
}
