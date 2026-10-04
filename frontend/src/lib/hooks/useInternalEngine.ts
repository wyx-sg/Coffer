// frontend/src/lib/hooks/useInternalEngine.ts — TanStack Query bindings for the
// Coffer's own operating settings (spec internal-engine).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { internalEngineApi, type UpkeepPass } from "@/lib/api/internalEngine";
import { useToast } from "@/components/ui/toast";
import { internalEngineKey } from "@/lib/api/queryKeys";

export function useInternalEngineConfig() {
  return useQuery({
    queryKey: internalEngineKey,
    queryFn: () => internalEngineApi.get(),
  });
}

/** Change one unattended pass's switch or interval (spec internal-engine "Change one
 *  unattended pass per write").
 *
 *  One pass per call, and each half omitted unless it is being changed: the
 *  Memory page's popover toggles one row at a time, and a body carrying every
 *  field would make each toggle a chance to write back a stale copy of the rest. */
export function useSetUpkeep() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({
      pass,
      enabled,
      interval_s,
    }: {
      pass: UpkeepPass;
      enabled?: boolean;
      interval_s?: number | null;
    }) =>
      internalEngineApi.setUpkeep({
        pass,
        ...(enabled === undefined ? {} : { enabled }),
        ...(interval_s === undefined || interval_s === null ? {} : { interval_s }),
        // `null` is "back to this pass's own default", which a null body field
        // cannot say — the server reads this flag for it instead.
        use_default_interval: interval_s === null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: internalEngineKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
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
