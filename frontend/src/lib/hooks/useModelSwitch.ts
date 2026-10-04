// frontend/src/lib/hooks/useModelSwitch.ts — review, then apply, one agent's model change.
//
// Opening the review asks the daemon for the files the change writes (nothing
// is written); the connection test already passed in the form (useModelSwitchTest).
// Apply sends back the fingerprints the
// preview read: when a file changed on disk since, the daemon refuses
// (CONFIG_FILE_STALE) and the review offers Reload preview instead of writing.
import { useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { modelSwitchApi, type ModelSwitchIn } from "@/lib/api/modelSwitch";
import { agentProvidersKey, agentsKey, providersKey } from "@/lib/api/queryKeys";

export function useModelSwitchReview(request: ModelSwitchIn, open: boolean) {
  const qc = useQueryClient();
  const preview = useMutation({ mutationFn: (b: ModelSwitchIn) => modelSwitchApi.preview(b) });
  const apply = useMutation({
    mutationFn: (b: ModelSwitchIn) => modelSwitchApi.apply(b),
    onSuccess: () => {
      // The agent's record names its connection and model; its
      // catalogue and proxy route follow the connection.
      void qc.invalidateQueries({ queryKey: providersKey });
      void qc.invalidateQueries({ queryKey: agentsKey });
      void qc.invalidateQueries({ queryKey: agentProvidersKey });
      void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "proxy" });
    },
  });

  const { mutate: runPreview, reset: resetPreview } = preview;
  const { reset: resetApply } = apply;

  const load = () => {
    resetApply();
    resetPreview();
    runPreview(request);
  };

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one review per opening
  }, [open]);

  const seen = Object.fromEntries((preview.data?.files ?? []).map((f) => [f.path, f.fingerprint]));
  const stale = apply.error instanceof ApiError && apply.error.code === "CONFIG_FILE_STALE";

  return {
    preview,
    apply,
    stale,
    /** The preview could not be made (the connection is off, the agent is off…). */
    previewError: preview.error,
    run: () => apply.mutate({ ...request, seen }),
    reload: load,
    reset: () => {
      resetApply();
      resetPreview();
    },
  };
}
