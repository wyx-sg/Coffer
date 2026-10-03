// src/lib/hooks/useToolReach.ts — the write half of one custom tool's inherited reach control: Same as the group
// (`null`) or the tool's own agent list, saved on every change through the tool's reach endpoint. A failed write
// stays in the popover as a failure with Retry, never a toast (the shared reach rule).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { customToolsApi, type CustomToolGroup } from "@/lib/api/customTools";
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
    mutationFn: (agents: string[] | null) => customToolsApi.setToolReach(group, tool, agents),
    onSuccess: (next: CustomToolGroup) => {
      qc.setQueryData(customToolGroupKey(next.name), next);
      void qc.invalidateQueries({ queryKey: customToolsKey });
      void qc.invalidateQueries({ queryKey: resourcesKey });
    },
  });

  /** `agents`: the override's uids, `null` to follow the group; `changed`: the uid just ticked. */
  const save = (agents: string[] | null, changed: string | null = null) => {
    clearTimeout(timer.current);
    setFailure(null);
    setState("applying");
    write.mutate(agents, {
      onSuccess: () => {
        setState("saved");
        timer.current = setTimeout(() => setState("idle"), SAVED_MS);
      },
      onError: (error) => {
        setState("idle");
        setFailure({
          uid: changed,
          message: translateApiError(t, error),
          retry: () => save(agents, changed),
        });
      },
    });
  };
  return { save, state, failure, pending: write.isPending };
}
