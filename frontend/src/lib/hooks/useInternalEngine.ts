// frontend/src/lib/hooks/useInternalEngine.ts — TanStack Query bindings for the
// global internal-engine model selection (spec provider-switching).
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

/** Change one unattended pass's switch or interval (spec provider-switching E3a).
 *
 *  One pass per call, and each half omitted unless it is being changed: the
 *  settings card toggles one row at a time, and a body carrying all three would
 *  make every toggle a chance to write back a stale copy of the other two. */
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

/** Bound one call to Coffer's own model; `null` returns it to the default.
 *
 *  A separate mutation from the model above for the reason `useSetUpkeep`
 *  records: one setting per request, so changing the bound cannot write back a
 *  stale copy of the model beside it. */
export function useSetModelTimeout() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (seconds: number | null) => internalEngineApi.setModelTimeout(seconds),
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
