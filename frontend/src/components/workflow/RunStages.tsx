// frontend/src/components/workflow/RunStages.tsx
// The shape of the work: the run's stages in the order the template wrote
// them, each with its nodes inside it.
//
// Coffer attaches no meaning to a stage key (FR-003), so nothing here maps a
// key onto an icon, a colour or a phase name — a stage is its user-chosen
// display name and its position, and a template with eight stages named by
// somebody else's process renders exactly as well as the seeded one.
//
// Nothing here advances the run (FR-052). "Add task" is the one control left,
// and it advances nothing: it opens a NEW conversation, which is where every
// decision now happens.
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { RunDetail } from "@/lib/api/workflow";
import { ActionGate } from "./ActionGate";
import { RunNodeRow } from "./RunNodeRow";

interface Props {
  detail: RunDetail;
  machine: string;
  /** Opens the "add an unplanned task" dialog for this stage (FR-028). */
  onAddTask: (stageKey: string) => void;
}

export function RunStages({ detail, machine, onAddTask }: Props) {
  const { t } = useTranslation();
  const { run, stages } = detail;

  return (
    <ol className="space-y-4">
      {stages.map((stage, index) => (
        <li key={stage.key} className="rounded-lg border border-border bg-card p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">{index + 1}</span>
              <h3 className="text-base font-medium">{stage.name}</h3>
              {stage.key === run.current_stage_key ? (
                <Badge variant="secondary">{t("workflow.stage.here")}</Badge>
              ) : null}
              {stage.optional ? (
                <Badge variant="outline">{t("workflow.stage.optional")}</Badge>
              ) : null}
            </div>
            <ActionGate ownedHere={run.owned_here} machine={machine}>
              <Button
                size="sm"
                variant="ghost"
                disabled={!run.owned_here}
                onClick={() => onAddTask(stage.key)}
              >
                <Plus aria-hidden />
                {t("workflow.adhoc.add")}
              </Button>
            </ActionGate>
          </div>

          <ul className="space-y-2">
            {stage.nodes.map((node) => (
              <RunNodeRow
                key={node.key}
                node={node}
                runId={run.id}
                isCurrent={node.key === run.current_node_key && stage.key === run.current_stage_key}
              />
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}
