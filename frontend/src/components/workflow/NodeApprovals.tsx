// frontend/src/components/workflow/NodeApprovals.tsx
// The approvals THIS task raised, INSIDE the task's conversation (FR-039).
//
// In the thread and not above it: the agent asking to create a merge request
// is a thing it did in the conversation, and it reads as the last turn rather
// than as a banner over the page. The developer scrolls to the bottom to see
// what is going on and the decision is there, under the message that led to
// it — which is the whole reason approvals live on this page at all.
//
// This is also the one place a button survives the move to conversations
// (FR-052): Approve / Reject is a decision about an exact payload, and a
// payload cannot honestly be approved by typing "ok" into a composer.
//
// Renders NOTHING when this task has nothing waiting — an empty "no approvals"
// card would compete for attention every day for the one day it matters.
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflowApprovals } from "@/lib/hooks/useWorkflowApprovals";
import { ApprovalCard } from "./ApprovalCard";

interface Props {
  runId: string;
  /**
   * The id of the attempt whose approvals these are. An approval carries the
   * attempt that raised it, so filtering on it — rather than on the node —
   * keeps a previous attempt's decision off the current one's page.
   */
  attemptId: string | null | undefined;
}

export function NodeApprovals({ runId, attemptId }: Props) {
  const { t } = useTranslation();
  const { data, isPending } = useWorkflowApprovals({ runId, status: "pending" });

  if (!attemptId) return null;
  if (isPending) return <Skeleton className="h-24 w-full" />;
  const items = (data ?? []).filter((approval) => approval.attempt_id === attemptId);
  if (items.length === 0) return null;

  return (
    <section className="space-y-3 pt-2" aria-label={t("workflow.approval.sectionLabel")}>
      <p className="text-sm font-medium">
        {t("workflow.approval.sectionTitle", { count: items.length })}
      </p>
      {items.map((approval) => (
        <ApprovalCard key={approval.id} approval={approval} />
      ))}
    </section>
  );
}
