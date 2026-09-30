// src/lib/hooks/useClis.ts — TanStack Query bindings for the commands managed skills require (/clis).
//
// Reads: the list (problems first) and one command. Writes: Check again, which
// re-probes every command and writes the fresh answer straight into the cache.
// Coffer never installs a command: fixing one is handed to an agent
// (`Cli.handoff`). The sidebar's attention signal is derived from the same list
// query the page reads.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { clisApi } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliKey, clisKey } from "@/lib/api/queryKeys";

export function useClis() {
  return useQuery({ queryKey: clisKey, queryFn: () => clisApi.list() });
}

export function useCli(command: string) {
  return useQuery({
    queryKey: cliKey(command),
    queryFn: () => clisApi.get(command),
    enabled: !!command,
  });
}

function useToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

/** Check again for every command: the answer replaces the list. */
export function useCheckClis() {
  const qc = useQueryClient();
  const onError = useToastError();
  return useMutation({
    mutationFn: () => clisApi.checkAll(),
    onSuccess: (list) => {
      qc.setQueryData(clisKey, list);
      // The per-command details were probed too.
      void qc.invalidateQueries({ queryKey: clisKey, predicate: (q) => q.queryKey.length > 1 });
    },
    onError,
  });
}

/** Whether the sidebar's CLIs entry carries a dot: any required command that
 *  is missing, too old or not logged in — the same rows the attention list
 *  reports as kind `cli`. `false` while loading or after a failed read. */
export function useClisAttention(): boolean {
  const { data } = useClis();
  return (data?.items ?? []).some((cli) => cli.status !== "ready");
}
