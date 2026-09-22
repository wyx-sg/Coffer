// frontend/src/lib/hooks/useWorkflowRun.ts — one run: its stages and nodes,
// its node actions, its ad-hoc tasks and its artifacts (spec workflow,
// FR-019..FR-031, FR-041/FR-043, FR-045).
//
// A run has NO conversation of its own (FR-030): every conversation belongs to
// one task, so there is no run-level message hook here and no `/messages`
// route to call. What the developer says, they say in a node's own
// conversation, through the ordinary chat layer.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { workflowApi } from "@/lib/api/workflow";
import type { AdhocTask, RunDetail } from "@/lib/api/workflow";
import { workflowArtifactsKey, workflowRunKey, workflowRunsKey } from "@/lib/api/queryKeys";
import { useToast } from "@/components/ui/toast";

/** How often an advancing run re-reads itself. */
const LIVE_POLL_MS = 3_000;

/** True while the run could move on its own without a command from here. */
function isLive(detail: RunDetail | undefined): boolean {
  return detail?.run.status === "running";
}

/** Choose who runs one task, on what, before it runs (FR-071). Invalidates the
 *  run, because the task's row is where the answer is read back from. */
export function useAssignNode(runId: string, nodeKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { agent: string | null; model: string | null; effort: string | null }) =>
      workflowApi.assignNode(runId, nodeKey, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workflowRunKey(runId) });
    },
  });
}

/** Rewrite a run's title and description (FR-070). Invalidates the run and
 *  the list, because both print the words that just changed. */
export function useRelabelRun(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; description: string | null }) =>
      workflowApi.relabelRun(runId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workflowRunKey(runId) });
      void qc.invalidateQueries({ queryKey: workflowRunsKey });
    },
  });
}

/**
 * One run with its stages, nodes and latest attempts. Polls while the run is
 * running: a node completing and the next one opening is exactly the thing the
 * developer opened this page to watch, and nothing pushes it.
 */
export function useWorkflowRun(runId: string) {
  return useQuery({
    queryKey: workflowRunKey(runId),
    queryFn: () => workflowApi.getRun(runId),
    enabled: runId.length > 0,
    refetchInterval: (query) => (isLive(query.state.data) ? LIVE_POLL_MS : false),
    refetchIntervalInBackground: false,
  });
}

/** Every artifact the run produced, attributed to node and attempt (FR-031). */
/** One file's contents, for the preview (FR-064). Never refetched on its
 *  own: a run's file is written once by the task that produced it, and an
 *  uploaded input does not change under the developer who uploaded it. */
export function useWorkflowRunFile(runId: string, path: string | null) {
  return useQuery({
    queryKey: [...workflowArtifactsKey(runId), "file", path],
    queryFn: () => workflowApi.readFile(runId, path ?? ""),
    enabled: runId.length > 0 && path !== null,
    staleTime: Infinity,
  });
}

export function useWorkflowArtifacts(runId: string, enabled = true) {
  return useQuery({
    queryKey: workflowArtifactsKey(runId),
    queryFn: () => workflowApi.listArtifacts(runId),
    enabled: enabled && runId.length > 0,
  });
}

/**
 * Add an unplanned task to a stage of a running run (FR-028). It joins as a
 * node keyed `adhoc:<slug>` and opens with the same shared context as any
 * template node — which is why it is added here and not run outside the run.
 */
export function useAddAdhocTask(runId: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (body: AdhocTask) => workflowApi.addAdhocTask(runId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workflowRunKey(runId) });
      void qc.invalidateQueries({ queryKey: workflowRunsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Say something to one task (FR-068). What it means is the daemon's answer, so
 * this hook carries no rules of its own: it sends the sentence and re-reads the
 * run, because the sentence may have queued a brief, carried an attempt on, or
 * opened the next one.
 */
export function useSayToTask(runId: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ nodeKey, text }: { nodeKey: string; text: string }) =>
      workflowApi.sayToNode(runId, nodeKey, text),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workflowRunKey(runId) });
      void qc.invalidateQueries({ queryKey: workflowRunsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Copy the run's artifacts into a knowledge collection (FR-043). The run's own
 * directory is untouched, so this is a copy and the page says so.
 */
export function usePromoteArtifacts(runId: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (collection: string) => workflowApi.promoteArtifacts(runId, collection),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: workflowArtifactsKey(runId) });
      toast.success(
        t("workflow.artifacts.promoted", {
          count: result.copied,
          collection: result.collection,
        }),
      );
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
