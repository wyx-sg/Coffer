// frontend/src/lib/hooks/useAgentTranscripts.ts — TanStack Query binding for the
// read-only agent conversation list.
//
// Listing pages on demand: the component owns page/pageSize/search and the hook
// fetches exactly one page (limit/offset) per query, keyed by the full params so
// each page caches independently. `keepPreviousData` keeps the current page
// visible while the next one loads — no blank flash on page/search change.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listTranscripts, type TranscriptListParams } from "@/lib/api/agentTranscripts";

/** Default page size for the transcript history list. */
export const TRANSCRIPTS_PAGE_SIZE = 10;

/** Search/filter/sort inputs (everything but the page window). */
export type TranscriptFilters = Omit<TranscriptListParams, "limit" | "offset">;

// ---------------------------------------------------------------------------
// Query key builder — hierarchical under ["agents", name] so a name-level
// invalidation sweeps conversations too. Export so components can invalidate.
// ---------------------------------------------------------------------------

export const transcriptsKey = (name: string, params?: TranscriptListParams) =>
  params
    ? (["agents", name, "conversations", params] as const)
    : (["agents", name, "conversations"] as const);

// ---------------------------------------------------------------------------
// Query: list one page of transcript sessions for an agent
// ---------------------------------------------------------------------------

export function useAgentTranscripts(name: string, params: TranscriptListParams = {}) {
  return useQuery({
    queryKey: transcriptsKey(name, params),
    queryFn: () => listTranscripts(name, params),
    // Keep the current page on screen while a new page/search key loads — no
    // blank flash on each keystroke or page step.
    placeholderData: keepPreviousData,
    enabled: !!name,
  });
}
