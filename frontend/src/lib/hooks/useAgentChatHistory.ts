// frontend/src/lib/hooks/useAgentChatHistory.ts — TanStack Query bindings for
// agent transcript listing and distillation (Spec 007 extension, Task 12).

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  distillTranscript,
  listTranscripts,
  type DistillRequest,
  type TranscriptListParams,
} from "@/lib/api/agentChat";
import { useToast } from "@/components/ui/toast";

/** Server page size for the transcript history list (each load-more fetch). */
export const TRANSCRIPTS_PAGE_SIZE = 100;

/** Search/filter/sort inputs that key the transcript query. */
export type TranscriptFilters = Omit<TranscriptListParams, "limit" | "offset">;

// ---------------------------------------------------------------------------
// Query key builder — hierarchical under ["agents", name] so a name-level
// invalidation sweeps conversations too. Export so components can invalidate.
// ---------------------------------------------------------------------------

export const transcriptsKey = (name: string, filters?: TranscriptFilters) =>
  filters
    ? (["agents", name, "conversations", filters] as const)
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
// Query: list transcript sessions for an agent
// ---------------------------------------------------------------------------

export function useAgentTranscripts(name: string, filters: TranscriptFilters = {}) {
  return useInfiniteQuery({
    queryKey: transcriptsKey(name, filters),
    queryFn: ({ pageParam }) =>
      listTranscripts(name, {
        ...filters,
        limit: TRANSCRIPTS_PAGE_SIZE,
        offset: pageParam as number,
      }),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const next = last.offset + last.limit;
      return next < last.total ? next : undefined;
    },
    // Keep showing the current page while a new filter/sort key loads — no
    // blank flash on each keystroke or sort toggle.
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
