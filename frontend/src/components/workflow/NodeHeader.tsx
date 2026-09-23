// frontend/src/components/workflow/NodeHeader.tsx
// The band above a task's conversation: what this task is, where it sits and
// how far it got. NO CONTROLS — a run is driven by talking to its tasks,
// so everything the developer can do to this one is in the thread
// below and this band only states facts.
//
// Split out of the page so the page is the LAYOUT — header, thread, context —
// and this is what the header says. They were one file and the file was the
// layout plus every badge in it, which is the shape a page takes on right
// before nobody can find anything in it.
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { NodeStatusBadge } from "@/components/workflow/WorkflowStatusBadge";
import type { Node, Run, RunStage } from "@/lib/api/workflow";

interface Props {
  run: Run;
  stage: RunStage;
  node: Node;
  back: { to: string; label: string };
}

export function NodeHeader({ run, stage, node, back }: Props) {
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
