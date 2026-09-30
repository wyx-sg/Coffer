// frontend/src/lib/hooks/useAgentTranscripts.ts — TanStack Query binding for the
// read-only agent conversation list.
//
// Listing pages on demand: the component owns page/pageSize/search and the hook
// fetches exactly one page (limit + the previous page's cursor) per query, keyed
// by the full params so each page caches independently. `keepPreviousData` keeps the current page
// visible while the next one loads — no blank flash on page/search change.

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listTranscripts,
  readTranscriptSession,
  type TranscriptListParams,
} from "@/lib/api/agentTranscripts";
import { agentTranscriptSessionKey, agentTranscriptsKey } from "@/lib/api/queryKeys";

/** Sessions per page of the Sessions tab's list ("Load more" reads the next). */
export const TRANSCRIPTS_PAGE_SIZE = 30;

// ---------------------------------------------------------------------------
// Query: list one page of transcript sessions for an agent
// ---------------------------------------------------------------------------

export function useAgentTranscripts(agentUid: string, params: TranscriptListParams = {}) {
  return useQuery({
    queryKey: agentTranscriptsKey(agentUid, params),
    queryFn: () => listTranscripts(agentUid, params),
    // Keep the current page on screen while a new page/search key loads — no
    // blank flash on each keystroke or page step.
    placeholderData: keepPreviousData,
    enabled: !!agentUid,
  });
}

// ---------------------------------------------------------------------------
// Query: read ONE session — summary plus a window of its turns
// ---------------------------------------------------------------------------

/** Default turns per page when reading one conversation. */
export const TRANSCRIPT_TURNS_PAGE_SIZE = 200;

export function useTranscriptSession(agentUid: string, sourcePath: string, offset = 0) {
  return useQuery({
    queryKey: agentTranscriptSessionKey(agentUid, sourcePath, offset),
    queryFn: () =>
      readTranscriptSession(agentUid, sourcePath, {
        limit: TRANSCRIPT_TURNS_PAGE_SIZE,
        offset,
      }),
    // Keep the turns on screen while the next window loads, so paging through a
    // long conversation does not blank the page between pages.
    placeholderData: keepPreviousData,
    enabled: !!agentUid && !!sourcePath,
  });
}

// ---------------------------------------------------------------------------
// Refresh: re-read every listing page and open session of an agent
// ---------------------------------------------------------------------------

/** Drops the agent's cached transcript listing and sessions so they are read
 *  again — the answer to a session file that moved after the list was read. */
export function useRefreshTranscripts(agentUid: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: agentTranscriptsKey(agentUid) });
}
