// frontend/src/lib/hooks/useHistory.ts — TanStack Query bindings for the
// cross-agent transcript history surface (ADR-022). Mirrors useChannels:
// queries under a "history" key, mutations toast on error via translateApiError.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { historyApi, type HistorySearchOpts } from "@/lib/api/history";
import { useToast } from "@/components/ui/toast";

export function historySearchKey(query: string, opts: HistorySearchOpts) {
  return ["history", "search", query, opts] as const;
}

export function historySessionKey(agent: string, sessionId: string) {
  return ["history", "session", agent, sessionId] as const;
}

/**
 * Full-text search across indexed transcripts. Disabled until the query is
 * non-empty so an empty box never fans out a request; results stay fresh for
 * 30s since the index only changes on an explicit reindex.
 */
export function useHistorySearch(query: string, opts: HistorySearchOpts = {}) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: historySearchKey(trimmed, opts),
    queryFn: () => historyApi.search(trimmed, opts),
    enabled: trimmed.length > 0,
    staleTime: 30_000,
  });
}

/** Browse one session's scrubbed turns (read-only). */
export function useHistorySession(agent: string | null, sessionId: string | null) {
  return useQuery({
    queryKey: historySessionKey(agent ?? "", sessionId ?? ""),
    queryFn: () => historyApi.browseSession(agent as string, sessionId as string),
    enabled: Boolean(agent) && Boolean(sessionId),
    staleTime: 60_000,
  });
}

/**
 * Re-index transcripts, then invalidate every history search so the next
 * search reflects the freshly indexed sessions. Toasts on error.
 */
export function useHistoryReindex() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (agent?: string) => historyApi.reindex(agent),
    onSuccess: (out) => {
      void qc.invalidateQueries({ queryKey: ["history", "search"] });
      toast.success(t("history.reindexed", { indexed: out.indexed }));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
