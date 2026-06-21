// frontend/src/lib/hooks/useAgentChatHistory.ts — TanStack Query bindings for
// agent transcript listing and distillation (Spec 007 extension, Task 12).
//
// Listing pages on demand: the component owns page/pageSize/search and the hook
// fetches exactly one page (limit/offset) per query, keyed by the full params so
// each page caches independently. `keepPreviousData` keeps the current page
// visible while the next one loads — no blank flash on page/search change.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  distillTranscript,
  listTranscripts,
  type DistillRequest,
  type TranscriptListParams,
} from "@/lib/api/agentChat";
import { useToast } from "@/components/ui/toast";

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
// Shared onError → toast helper (mirrors useSkills.ts pattern)
// ---------------------------------------------------------------------------

function useChatHistoryToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

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

// ---------------------------------------------------------------------------
// Mutation: distill a session to memory facts
// ---------------------------------------------------------------------------

export function useDistillTranscript(name: string) {
  const qc = useQueryClient();
  const onError = useChatHistoryToastError();
  return useMutation({
    mutationFn: (body: DistillRequest) => distillTranscript(name, body),
    onSuccess: () => {
      // Invalidate the transcript list (session list may not change but refresh
      // is cheap and keeps UI consistent) and the memory-stores list (new facts
      // may have been written to the projected store).
      void qc.invalidateQueries({ queryKey: transcriptsKey(name) });
      void qc.invalidateQueries({ queryKey: ["memory-stores"] });
    },
    onError,
  });
}
