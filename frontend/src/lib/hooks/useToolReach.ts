// src/lib/hooks/useToolReach.ts — the write half of one custom tool's inherited reach control: Same as the group
// (`inherit`), every agent (`all`) or the tool's own agent list (`chosen`), saved on every change through the tool's reach endpoint. A failed write
// stays in the popover as a failure with Retry, never a toast (the shared reach rule).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { customToolsApi, type CustomToolGroup, type ToolReach } from "@/lib/api/customTools";
import { translateApiError } from "@/lib/api/errors";
import { customToolGroupKey, customToolsKey, resourcesKey } from "@/lib/api/queryKeys";
import type { ReachFailure } from "@/lib/reach/reachState";
import type { SaveState } from "@/lib/reach/useReachWrites";

const SAVED_MS = 2000;

export function useToolReach(group: string, tool: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const [state, setState] = useState<SaveState>("idle");
  const [failure, setFailure] = useState<ReachFailure | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const write = useMutation({
    mutationFn: (reach: ToolReach) => customToolsApi.setToolReach(group, tool, reach),
    onSuccess: (next: CustomToolGroup) => {
      qc.setQueryData(customToolGroupKey(next.name), next);
      void qc.invalidateQueries({ queryKey: customToolsKey });
      void qc.invalidateQueries({ queryKey: resourcesKey });
    },
  });

  /** `reach`: what to write; `changed`: the uid just ticked. */
  const save = (reach: ToolReach, changed: string | null = null) => {
    clearTimeout(timer.current);
    setFailure(null);
    setState("applying");
    write.mutate(reach, {
      onSuccess: () => {
        setState("saved");
        timer.current = setTimeout(() => setState("idle"), SAVED_MS);
      },
      onError: (error) => {
        setState("idle");
        setFailure({
          uid: changed,
          message: translateApiError(t, error),
          retry: () => save(reach, changed),
        });
      },
    });
  };
  return { save, state, failure, pending: write.isPending };
}
