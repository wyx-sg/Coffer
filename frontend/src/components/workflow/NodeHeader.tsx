// frontend/src/components/workflow/NodeHeader.tsx
// The band above a task's conversation: what this task is, where it sits, how
// far it got, and the one control that is not a sentence (FR-063).
//
// Split out of the page so the page is the LAYOUT — header, thread, context —
// and this is what the header says. They were one file and the file was the
// layout plus every badge in it, which is the shape a page takes on right
// before nobody can find anything in it.
import { useTranslation } from "react-i18next";
import { CornerUpLeft } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NodeStatusBadge } from "@/components/workflow/WorkflowStatusBadge";
import type { Node, Run, RunStage } from "@/lib/api/workflow";

interface Props {
  run: Run;
  stage: RunStage;
  node: Node;
  back: { to: string; label: string };
  /** False when there is no edge out of this stage, or no right to take one. */
  canSendBack: boolean;
  onSendBack: () => void;
}

export function NodeHeader({ run, stage, node, back, canSendBack, onSendBack }: Props) {
  const { t } = useTranslation();
  return (
    <PageHeader
      back={back}
      title={node.name}
      subtitle={t("workflow.nodeConversation.subtitle", {
        run: run.title,
        stage: stage.name,
        type: t(`workflow.node.types.${node.type}`),
      })}
      actions={
        canSendBack ? (
          <Button variant="outline" size="sm" onClick={onSendBack}>
            <CornerUpLeft className="mr-1 size-3.5" aria-hidden />
            {t("workflow.sendBack.action")}
          </Button>
        ) : undefined
      }
      badges={
        <div className="flex flex-wrap items-center gap-2">
          <NodeStatusBadge status={node.status} />
          <Badge variant="outline">{t("workflow.node.attempt", { count: node.attempt })}</Badge>
          {node.adhoc ? <Badge variant="secondary">{t("workflow.node.unplanned")}</Badge> : null}
          {node.skill ? <Badge variant="outline">{node.skill}</Badge> : null}
        </div>
      }
    />
  );
}
