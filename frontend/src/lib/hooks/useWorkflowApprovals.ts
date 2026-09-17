// frontend/src/lib/hooks/useWorkflowApprovals.ts — the gate between a run and
// the outside world (spec workflow, FR-033..FR-039, FR-045).
//
// An approval carries the EXACT payload that will execute. Nothing in this
// file summarises, truncates or reshapes it: the surface renders what the
// daemon sent, because the payload being verbatim is the entire reason the
// developer can answer the question.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { workflowApi } from "@/lib/api/workflow";
import type { Approval, ApprovalStatus } from "@/lib/api/workflow";
import {
  workflowApprovalsKey,
  workflowApprovalsRootKey,
  workflowRunKey,
  workflowRunsKey,
} from "@/lib/api/queryKeys";
import { useToast } from "@/components/ui/toast";

/** A pending approval blocks a run; it must not need a refresh to appear. */
const PENDING_POLL_MS = 5_000;

export interface ApprovalFilters {
  /** Narrow to one run. Omit for every run's approvals. */
  runId?: string;
  status?: ApprovalStatus;
}

/**
 * Approvals, pending first. Polls while any is pending, both because one
 * arrives without being asked for and because an approval expires on its own
 * (FR-037) — an expiry the page never notices is an approval the developer
 * would decide too late.
 */
export function useWorkflowApprovals(filters: ApprovalFilters = {}) {
  return useQuery({
    queryKey: workflowApprovalsKey({ runId: filters.runId, status: filters.status }),
    queryFn: async () =>
      (await workflowApi.listApprovals({ runId: filters.runId, status: filters.status })).items,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((a: Approval) => a.status === "pending")
        ? PENDING_POLL_MS
        : false,
    refetchIntervalInBackground: false,
  });
}

export interface DecisionVars {
  approvalId: string;
  decision: "approved" | "rejected";
  /** Free text the node can act on — required by the UI when rejecting. */
  comment?: string | null;
  /** Remember this tool's write-class judgement so it is not asked twice
   *  (FR-036). */
  rememberToolClass?: "read" | "write" | null;
}

/**
 * Approve or reject one approval. Idempotent on the wire (FR-038), so a
 * double-click cannot execute a held call twice.
 *
 * The run is invalidated as well as the approvals list: approving releases the
 * held call, and the node that was waiting moves.
 */
export function useDecideApproval(runId?: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ approvalId, decision, comment, rememberToolClass }: DecisionVars) =>
      workflowApi.decideApproval(approvalId, {
        decision,
        comment,
        remember_tool_class: rememberToolClass ?? null,
      }),
    onSuccess: (approval) => {
      void qc.invalidateQueries({ queryKey: workflowApprovalsRootKey });
      void qc.invalidateQueries({ queryKey: workflowRunKey(runId ?? approval.run_id) });
      void qc.invalidateQueries({ queryKey: workflowRunsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
