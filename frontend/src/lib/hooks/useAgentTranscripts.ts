// frontend/src/lib/hooks/useAgentTranscripts.ts — TanStack Query binding for the
// read-only agent conversation list.
//
// Listing pages on demand: the component owns page/pageSize/search and the hook
// fetches exactly one page (limit/offset) per query, keyed by the full params so
// each page caches independently. `keepPreviousData` keeps the current page
// visible while the next one loads — no blank flash on page/search change.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  listTranscripts,
  readTranscriptSession,
  type TranscriptListParams,
} from "@/lib/api/agentTranscripts";
import { agentTranscriptSessionKey, agentTranscriptsKey } from "@/lib/api/queryKeys";

/** Default page size for the transcript history list. */
export const TRANSCRIPTS_PAGE_SIZE = 10;

/** Search/filter/sort inputs (everything but the page window). */
export type TranscriptFilters = Omit<TranscriptListParams, "limit" | "offset">;

// ---------------------------------------------------------------------------
// Query: list one page of transcript sessions for an agent
// ---------------------------------------------------------------------------

export function useAgentTranscripts(name: string, params: TranscriptListParams = {}) {
  return useQuery({
    queryKey: agentTranscriptsKey(name, params),
    queryFn: () => listTranscripts(name, params),
    // Keep the current page on screen while a new page/search key loads — no
    // blank flash on each keystroke or page step.
    placeholderData: keepPreviousData,
    enabled: !!name,
  });
}

// ---------------------------------------------------------------------------
// Query: read ONE session — summary plus a window of its turns
// ---------------------------------------------------------------------------

/** Default turns per page when reading one conversation. */
export const TRANSCRIPT_TURNS_PAGE_SIZE = 200;

export function useTranscriptSession(name: string, sourcePath: string, offset = 0) {
  return useQuery({
    queryKey: agentTranscriptSessionKey(name, sourcePath, offset),
    queryFn: () =>
      readTranscriptSession(name, sourcePath, {
        limit: TRANSCRIPT_TURNS_PAGE_SIZE,
        offset,
      }),
    // Keep the turns on screen while the next window loads, so paging through a
    // long conversation does not blank the page between pages.
    placeholderData: keepPreviousData,
    enabled: !!name && !!sourcePath,
  });
}
