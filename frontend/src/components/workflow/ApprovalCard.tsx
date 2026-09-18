// frontend/src/components/workflow/ApprovalCard.tsx
// One approval: the gate between a run and the outside world (FR-033/FR-034).
//
// THE PAYLOAD IS RENDERED VERBATIM. Not a summary, not the first line, not
// "call Jira with 3 arguments" — the exact arguments that will execute, as
// JSON, scrollable when long. A summary would ask the developer to approve
// something they cannot see, which is the one thing this surface exists to
// prevent. Nothing here truncates.
//
// Rejecting asks for a reason because the node can act on one (FR-021's
// feedback is the same idea): "no" with a reason redirects the work, "no"
// alone only stops it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useDecideApproval } from "@/lib/hooks/useWorkflowApprovals";
import { formatDateTime } from "@/lib/utils";
import type { Approval } from "@/lib/api/workflow";

export function ApprovalCard({ approval }: { approval: Approval }) {
  const { t } = useTranslation();
  const decide = useDecideApproval(approval.run_id);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");
  const [rememberRead, setRememberRead] = useState(false);

  const pending = approval.status === "pending";
  const toolName = approval.tool_name ?? t("workflow.approval.nodeAction");

  return (
    <Card className="border-status-warn/40">
      <CardHeader className="pb-3">
        <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
          <ShieldAlert className="size-5 text-status-warn" aria-hidden />
          {t("workflow.approval.title", { tool: toolName })}
          {!pending ? (
            <Badge variant="secondary">{t(`workflow.approval.status.${approval.status}`)}</Badge>
          ) : null}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {t("workflow.approval.expiresAt", { at: formatDateTime(approval.expires_at) })}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            {t("workflow.approval.payloadLabel")}
          </p>
          {/* Verbatim, scrollable, never elided. */}
          <pre className="max-h-96 overflow-auto rounded-md border border-border bg-muted p-3 font-mono text-xs">
            {JSON.stringify(approval.payload, null, 2)}
          </pre>
        </div>

        {pending ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={decide.isPending}
              onClick={() => {
                setComment("");
                setRememberRead(false);
                setApproveOpen(true);
              }}
            >
              {t("workflow.approval.approve")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={decide.isPending}
              onClick={() => {
                setReason("");
                setRejectOpen(true);
              }}
            >
              {t("workflow.approval.reject")}
            </Button>
          </div>
        ) : approval.decided_at ? (
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              {t("workflow.approval.decidedAt", { at: formatDateTime(approval.decided_at) })}
            </p>
            {/* The reason a rejection carried is what the node acts on, so a
                decided approval keeps saying it rather than only the verdict. */}
            {approval.comment ? <p className="text-sm">{approval.comment}</p> : null}
          </div>
        ) : null}
      </CardContent>

      <ConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title={t("workflow.approval.approveTitle", { tool: toolName })}
        description={t("workflow.approval.approveDescription")}
        confirmLabel={t("workflow.approval.approve")}
        variant="default"
        pending={decide.isPending}
        onConfirm={() =>
          decide.mutateAsync({
            approvalId: approval.id,
            decision: "approved",
            comment: comment.trim() || null,
            rememberToolClass: rememberRead ? "read" : null,
          })
        }
      >
        <Textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          placeholder={t("workflow.approval.commentPlaceholder")}
          aria-label={t("workflow.approval.commentLabel")}
        />
        {approval.tool_name ? (
          <div className="flex items-start gap-2">
            <Checkbox
              id={`remember-${approval.id}`}
              checked={rememberRead}
              onChange={(e) => setRememberRead(e.target.checked)}
              className="mt-0.5"
            />
            <Label htmlFor={`remember-${approval.id}`} className="text-sm font-normal leading-snug">
              {t("workflow.approval.rememberRead", { tool: approval.tool_name })}
            </Label>
          </div>
        ) : null}
      </ConfirmDialog>

      <ConfirmDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        title={t("workflow.approval.rejectTitle", { tool: toolName })}
        description={t("workflow.approval.rejectDescription")}
        confirmLabel={t("workflow.approval.reject")}
        pending={decide.isPending || reason.trim().length === 0}
        onConfirm={() =>
          decide.mutateAsync({
            approvalId: approval.id,
            decision: "rejected",
            comment: reason.trim(),
          })
        }
      >
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder={t("workflow.approval.reasonPlaceholder")}
          aria-label={t("workflow.approval.reasonLabel")}
        />
      </ConfirmDialog>
    </Card>
  );
}
