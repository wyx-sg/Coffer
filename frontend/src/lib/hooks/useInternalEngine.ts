// frontend/src/lib/hooks/useInternalEngine.ts — TanStack Query bindings for the
// global internal-engine model selection (spec provider-switching).
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

/** Set (or clear, with null) the model the internal engine runs on. */
export function useSetInternalEngineModel() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (model: string | null) => internalEngineApi.setModel(model),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: internalEngineKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
