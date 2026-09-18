// frontend/src/lib/hooks/useWorkflowRuns.ts — TanStack Query bindings for the
// workflow run LIST (spec workflow, FR-011/FR-012/FR-045).
//
// One run's detail, its nodes and its artifacts live in useWorkflowRun.ts;
// approvals in useWorkflowApprovals.ts. Templates are resources of kind
// `workflow` (FR-001) and have their own hook file (useWorkflowTemplates.ts)
// over the generic resource endpoint — there is no template endpoint and this
// file adds none.
//
// Every mutating command carries the caller's OBSERVED version (FR-015): the
// daemon refuses a stale one with the run's current version rather than
// applying it, which is why `version` is a caller argument here and never
// something a hook reads back out of the cache for you.
//
// The run SIGNALS (start / pause / resume / abort) are not here and have no
// hook: the run's own page offers nothing that advances or alters it (FR-052),
// so the web UI never issues one. The route stays in the contract for the CLI.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { workflowApi } from "@/lib/api/workflow";
import type { Run, RunCreate, RunStatus } from "@/lib/api/workflow";
import { workflowRunKey, workflowRunsKey, workflowRunsListKey } from "@/lib/api/queryKeys";
import { useMachines } from "@/lib/hooks/useMachines";
import { useToast } from "@/components/ui/toast";

/** How often the run list re-reads while anything is still advancing. */
const LIVE_POLL_MS = 5_000;

/** True while any run could move on its own, so the list is worth re-reading. */
function anyRunLive(runs: Run[] | undefined): boolean {
  return (runs ?? []).some((r) => r.status === "running");
}

/** Every run on this vault, newest first; narrowed to one status when given. */
export function useWorkflowRuns(status?: RunStatus) {
  return useQuery({
    queryKey: workflowRunsListKey(status),
    queryFn: async () => (await workflowApi.listRuns(status)).items,
    // A run advances in the background with nobody watching — the list is the
    // one surface that has to notice without being told.
    refetchInterval: (query) => (anyRunLive(query.state.data) ? LIVE_POLL_MS : false),
    refetchIntervalInBackground: false,
  });
}

/**
 * The machine a run belongs to, in words. A run this machine does not own is
 * read-only (FR-012), and saying *which* machine advances it is the whole
 * difference between a disabled button and a broken one.
 */
export function useMachineLabel(): (machineId: string) => string {
  const { data } = useMachines();
  return (machineId: string) =>
    data?.machines.find((m) => m.machine_id === machineId)?.name ?? machineId;
}

/**
 * Create a run from a template's uid and a title. The run lands in `draft` —
 * starting it is a separate signal, so the developer can mount inputs before
 * the first node opens.
 *
 * The uid rather than the label: the run freezes the template's snapshot at
 * creation, and the thing it freezes has to be the workflow the developer
 * picked rather than whatever that label named by the time the request landed.
 *
 * No toast on success: the caller navigates to the new run, which says more
 * than a toast would.
 */
export function useCreateRun() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (body: RunCreate) => workflowApi.createRun(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: workflowRunsKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Delete a run, its events, attempts, approvals and directory. */
export function useDeleteRun() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (runId: string) => workflowApi.deleteRun(runId),
    onSuccess: (_data, runId) => {
      // Drop the detail first so a stale detail view cannot refetch a 404.
      qc.removeQueries({ queryKey: workflowRunKey(runId) });
      void qc.invalidateQueries({ queryKey: workflowRunsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
