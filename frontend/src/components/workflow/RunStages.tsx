// frontend/src/components/workflow/RunStages.tsx
// Where the delivery is: the run's stages beside the tasks of the one being
// looked at.
//
// THE SAME PICTURE AS THE TEMPLATE EDITOR, drawn by the same component. A run
// is the template it froze with state on it, so a developer who has learned to
// read one has learned to read the other. What differs is what each row's
// trailing slot says — the editor counts tasks, because the question there is
// how much is in a stage; a run marks where it is, because that is the
// question here.
//
// Coffer attaches no meaning to a stage key, so nothing here maps a
// key onto an icon, a colour or a phase name — a stage is its user-chosen
// display name and its position, and a template with eight stages named by
// somebody else's process renders exactly as well as the seeded one.
//
// Nothing here advances the run. "Add task" is the one control left,
// and it advances nothing: it opens a NEW conversation, which is where every
// decision now happens.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { RunDetail } from "@/lib/api/workflow";
import { ActionGate } from "./ActionGate";
import { RunNodeRow } from "./RunNodeRow";
import { StageRailList } from "./StageRailList";

interface Props {
  detail: RunDetail;
  machine: string;
  /** Opens the "add an unplanned task" dialog for this stage. */
  onAddTask: (stageKey: string) => void;
}

export function RunStages({ detail, machine, onAddTask }: Props) {
  const { t } = useTranslation();
  const { run, stages } = detail;
  // Opens on the stage the run is actually at, because that is what the
  // developer came to look at. Clamped, so a template whose stage list this
  // build cannot match still shows something.
  const here = Math.max(
    stages.findIndex((stage) => stage.key === run.current_stage_key),
    0,
  );
  const [picked, setPicked] = useState(here);
  const selected = Math.min(picked, Math.max(stages.length - 1, 0));
  const stage = stages[selected];

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]">
      <StageRailList
        stages={stages.map((s) => ({
          key: s.key,
          name: s.name,
          optional: s.optional,
          trailing:
            s.key === run.current_stage_key ? (
              <Badge variant="secondary" className="shrink-0 px-1.5 py-0 text-[10px]">
                {t("workflow.stage.here")}
              </Badge>
            ) : undefined,
        }))}
        selected={selected}
        onSelect={setPicked}
      />

      {stage === undefined ? null : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
            <h3 className="min-w-[8rem] flex-1 truncate font-serif text-lg">{stage.name}</h3>
            <span className="shrink-0 text-sm text-muted-foreground">
              {t("workflow.templates.taskCount", { count: stage.nodes.length })}
            </span>
            <ActionGate ownedHere={run.owned_here} machine={machine}>
              <Button
                size="sm"
                variant="outline"
                disabled={!run.owned_here}
                onClick={() => onAddTask(stage.key)}
              >
                <Plus className="mr-1 size-3.5" aria-hidden />
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
        </div>
      )}
    </div>
  );
}
