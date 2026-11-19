// frontend/src/lib/hooks/useInternalEngine.ts — TanStack Query bindings for the
// Coffer's own operating settings (spec internal-engine).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { internalEngineApi } from "@/lib/api/internalEngine";
import { useToast } from "@/components/ui/toast";
import { internalEngineKey } from "@/lib/api/queryKeys";

export function useInternalEngineConfig() {
  return useQuery({
    queryKey: internalEngineKey,
    queryFn: () => internalEngineApi.get(),
  });
}

/** Set (or clear, with null) the model Coffer transcribes speech with. Clearing
 *  it is a real answer: with no model, a turn carrying audio hands the agent the
 *  file untouched and the recording never leaves the machine. */
export function useSetTranscribeModel() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (model: string | null) => internalEngineApi.setTranscribeModel(model),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: internalEngineKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
