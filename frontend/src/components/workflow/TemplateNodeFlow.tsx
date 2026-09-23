// frontend/src/components/workflow/TemplateNodeFlow.tsx
// The right half of the editor: one stage's tasks, in the order they run, each
// saying what it does.
//
// Down rather than across, and one per row: a stage's tasks are a sequence,
// and a row of chips reads as a set of options.
//
// THE STAGE'S OWN BUTTONS ARE NOT HERE. They are on the left, over the list
// they act on: an Edit sitting beside this panel's heading looks like it edits
// what the panel is showing, which is the tasks — and the one thing it must
// not be misread as is a way to edit a task.
//
// Nothing here says where work goes when something is found wrong, because a
// workflow draws no route back: the stages run in the order they sit
// in, and a finding is acted on by the developer holding it.
import { ChevronDown, Plus } from "lucide-react";
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplateTaskCard } from "@/components/workflow/TemplateTaskCard";
import type { TemplateStage } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  stage: TemplateStage;
  index: number;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
  /** Open a task's fields; `null` adds one to this stage. */
  onEditNode: (nodeIndex: number | null) => void;
  /** Asks to delete; the confirmation and the write are the caller's. */
  onDeleteNode: (nodeIndex: number) => void;
}

export function TemplateNodeFlow({
  stage,
  index,
  refusal,
  editor,
  onEditNode,
  onDeleteNode,
}: Props) {
  const { t } = useTranslation();
  const path = `stages[${index}]`;
  const label = stage.name.length > 0 ? stage.name : stage.key;

  return (
    <div className="space-y-4">
      {/* HOW MANY, beside the heading of the panel that is showing them. On
          the stage rows it was a bare number next to a button, which reads as
          the button's badge; here it is next to the thing it counts. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
        <h3 className="min-w-0 flex-1 truncate font-serif text-lg">{label}</h3>
        <span className="shrink-0 text-sm text-muted-foreground">
          {t("workflow.templates.taskCount", { count: stage.nodes.length })}
        </span>
        {stage.optional ? (
          <Badge variant="secondary">{t("workflow.templates.optional")}</Badge>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        {stage.nodes.map((node, nodeIndex) => (
          <Fragment key={node.key}>
            {nodeIndex > 0 ? (
              <ChevronDown className="ml-4 size-4 text-muted-foreground" aria-hidden />
            ) : null}
            <TemplateTaskCard
              node={node}
              onEdit={() => onEditNode(nodeIndex)}
              canDelete={stage.nodes.length > 1}
              disabled={editor.isSaving}
              onDelete={() => onDeleteNode(nodeIndex)}
            />
          </Fragment>
        ))}
      </div>

      <TemplateFieldError refusal={refusal} path={`${path}.nodes`} />
      <TemplateFieldError refusal={refusal} path={path} />

      <Button type="button" variant="outline" size="sm" onClick={() => onEditNode(null)}>
        <Plus className="mr-1 size-3.5" aria-hidden />
        {t("workflow.templates.addNode")}
      </Button>
    </div>
  );
}
