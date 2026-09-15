// frontend/src/lib/hooks/useAgentTranscripts.ts — TanStack Query binding for the
// read-only agent conversation list.
//
// Listing pages on demand: the component owns page/pageSize/search and the hook
// fetches exactly one page (limit/offset) per query, keyed by the full params so
// each page caches independently. `keepPreviousData` keeps the current page
// visible while the next one loads — no blank flash on page/search change.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listTranscripts, type TranscriptListParams } from "@/lib/api/agentTranscripts";
import { agentTranscriptsKey } from "@/lib/api/queryKeys";

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
