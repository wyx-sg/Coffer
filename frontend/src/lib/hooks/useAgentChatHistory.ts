// frontend/src/lib/hooks/useAgentChatHistory.ts — TanStack Query bindings for
// agent transcript listing and distillation (Spec 007 extension, Task 12).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { distillTranscript, listTranscripts, type DistillRequest } from "@/lib/api/agentChat";
import { useToast } from "@/components/ui/toast";

// ---------------------------------------------------------------------------
// Query key builder — hierarchical under ["agents", name] so a name-level
// invalidation sweeps conversations too. Export so components can invalidate.
// ---------------------------------------------------------------------------

export const transcriptsKey = (name: string) =>
  ["agents", name, "conversations"] as const;

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

export function useAgentTranscripts(name: string) {
  return useQuery({
    queryKey: transcriptsKey(name),
    queryFn: () => listTranscripts(name),
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
