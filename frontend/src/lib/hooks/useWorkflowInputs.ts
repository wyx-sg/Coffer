// frontend/src/lib/hooks/useWorkflowInputs.ts — what a run READS: knowledge
// collections, uploaded files and links (spec workflow, FR-032/FR-050/FR-051).
//
// Inputs are the developer's for the whole of a run's life, not only at
// creation, so this is a live list with three mutations rather than a field on
// the create dialog. Every mutation returns the WHOLE list, which is written
// straight into the cache: the server's answer is the authority on what is
// mounted, and a refetch after each edit would show the developer a stale list
// for one paint.
//
// Nothing here carries the run's `version`: an input is what the run reads,
// not where the run is, so mounting one never races the engine's position.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { workflowApi } from "@/lib/api/workflow";
import type { InputList, RunInputIn } from "@/lib/api/workflow";
import { workflowInputsKey } from "@/lib/api/queryKeys";
import { useToast } from "@/components/ui/toast";

/** The inputs mounted on this run, in the order the daemon lists them. */
export function useWorkflowInputs(runId: string, enabled = true) {
  return useQuery({
    queryKey: workflowInputsKey(runId),
    queryFn: async () => (await workflowApi.listInputs(runId)).items,
    enabled: enabled && runId.length > 0,
  });
}

/** Mount a knowledge collection or a link (FR-050). */
export function useAddWorkflowInput(runId: string) {
  return useInputMutation(runId, (input: RunInputIn) => workflowApi.addInput(runId, input));
}

/** Upload a file into the run's own directory and mount it (FR-051). */
export function useUploadWorkflowInput(runId: string) {
  return useInputMutation(runId, ({ file, label }: { file: File; label?: string | null }) =>
    workflowApi.uploadInput(runId, file, label),
  );
}

/** Unmount one input by its `ref` (FR-050). */
export function useRemoveWorkflowInput(runId: string) {
  return useInputMutation(runId, (inputRef: string) => workflowApi.removeInput(runId, inputRef));
}

/**
 * The shape the three mutations share: write the returned list into the cache,
 * report a refusal as a toast, and leave the run's own detail alone — mounting
 * an input does not move the run.
 */
function useInputMutation<TVars>(runId: string, mutationFn: (vars: TVars) => Promise<InputList>) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn,
    onSuccess: (list) => qc.setQueryData(workflowInputsKey(runId), list.items),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
