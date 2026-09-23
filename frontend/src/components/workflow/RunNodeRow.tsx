// frontend/src/components/workflow/RunNodeRow.tsx
// One node inside its stage: what it is, where it got to — and a way in.
//
// The whole row is a LINK to the node's conversation page and carries no
// buttons at all. Retry, skip, complete and feedback used to live
// here; they now live in the conversation, where the thing being decided is in
// front of the developer. What is left is a map pin: status, attempt, and a
// click that opens the task.
//
// An ad-hoc task renders here like any other node — same row, same status,
// same attribution — with one "unplanned" chip, because the whole point of
// an ad-hoc task is that unplanned work joins the run rather than happening beside it.
// Hiding it in a separate list would make the run's record untrue.
//
// The attempt number is always shown, not only when it is greater than one: a
// retry appends an attempt and the previous one survives, so "which
// attempt am I looking at" is a question this row must answer on its face.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn, formatDateTime } from "@/lib/utils";
import type { Node } from "@/lib/api/workflow";
import { NodeStatusBadge } from "./WorkflowStatusBadge";

interface Props {
  node: Node;
  runId: string;
  /** The node the run is sitting on right now. */
  isCurrent: boolean;
}

export function RunNodeRow({ node, runId, isCurrent }: Props) {
  const { t } = useTranslation();
  const latest = node.latest;
  return (
    <li data-testid={`node-${node.key}`}>
      <Link
        to={`/runs/${runId}/nodes/${encodeURIComponent(node.key)}`}
        aria-label={t("workflow.node.openConversation")}
        className={cn(
          "flex flex-col gap-3 rounded-md border border-border bg-background p-3 transition-colors hover:border-primary/50 hover:bg-muted/40",
          isCurrent && "border-primary/50 ring-1 ring-primary/20",
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{node.name}</span>
          <NodeStatusBadge status={node.status} />
          <Badge variant="outline">{t("workflow.node.attempt", { count: node.attempt })}</Badge>
          {node.adhoc ? <Badge variant="secondary">{t("workflow.node.unplanned")}</Badge> : null}
          <span className="text-xs text-muted-foreground">
            {t(`workflow.node.types.${node.type}`)}
            {node.skill ? ` · ${node.skill}` : ""}
          </span>
          <ChevronRight className="ml-auto size-4 text-muted-foreground" aria-hidden />
        </div>

        {latest?.failure_reason ? (
          <p className="text-sm text-destructive">
            {t(`workflow.node.failure.${latest.failure_reason}`)}
          </p>
        ) : null}
        {latest?.summary ? (
          <p className="max-w-prose text-sm text-muted-foreground">{latest.summary}</p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          {latest?.finished_at ? (
            <span>{t("workflow.node.finishedAt", { at: formatDateTime(latest.finished_at) })}</span>
          ) : latest?.started_at ? (
            <span>{t("workflow.node.startedAt", { at: formatDateTime(latest.started_at) })}</span>
          ) : null}
        </div>
      </Link>
    </li>
  );
}
