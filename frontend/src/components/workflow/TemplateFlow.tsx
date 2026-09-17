// frontend/src/components/workflow/TemplateFlow.tsx
// The template as a MAP: a box per stage, a box per task, and nothing else on
// screen (FR-061).
//
// The editor used to render every field of every task inline, so a four-task
// flow was a wall of forty controls and the shape of the work — which is the
// thing a template IS — could not be seen at all. Here the shape is all you
// see: the stages top to bottom in the order they run, the tasks inside them,
// and the feedback edges as return arrows. A detail is one click away, in the
// dialog of the thing it belongs to.
import { Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplateNodeDialog } from "@/components/workflow/TemplateNodeDialog";
import { TemplateStageBox } from "@/components/workflow/TemplateStageBox";
import { TemplateStageDialog } from "@/components/workflow/TemplateStageDialog";
import type { TemplateConfig } from "@/lib/api/workflow";
import { useAgents } from "@/lib/hooks/useAgents";
import { useSkills } from "@/lib/hooks/useSkills";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

/** Which dialog is open, and on what. `stage: null` means a new stage; a node
 *  with `node: null` means a new task in that stage. */
type Open =
  | { kind: "stage"; stage: number | null }
  | { kind: "node"; stage: number; node: number | null }
  | null;

interface Props {
  config: TemplateConfig;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
}

export function TemplateFlow({ config, refusal, editor }: Props) {
  const { t } = useTranslation();
  // Fetched once here rather than per task: a template with six tasks would
  // otherwise ask the daemon for the same two lists twelve times.
  const skills = (useSkills().data ?? []).map((s) => s.name);
  const agents = (useAgents().data ?? []).map((a) => a.name);
  const [open, setOpen] = useState<Open>(null);

  const close = () => setOpen(null);
  const openDialog = (next: Exclude<Open, null>) => {
    editor.reset();
    setOpen(next);
  };

  return (
    <div className="space-y-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        {t("workflow.templates.flowHint")}
      </p>

      {config.stages.map((stage, index) => (
        <TemplateStageBox
          key={stage.key}
          config={config}
          stage={stage}
          index={index}
          refusal={refusal}
          editor={editor}
          onEditStage={() => openDialog({ kind: "stage", stage: index })}
          onEditNode={(node) => openDialog({ kind: "node", stage: index, node })}
        />
      ))}

      <TemplateFieldError refusal={refusal} path="stages" />

      <Button
        type="button"
        variant="outline"
        onClick={() => openDialog({ kind: "stage", stage: null })}
      >
        <Plus className="mr-1 size-4" aria-hidden />
        {t("workflow.templates.addStage")}
      </Button>

      {open?.kind === "stage" ? (
        <TemplateStageDialog
          config={config}
          index={open.stage}
          refusal={refusal}
          editor={editor}
          onClose={close}
        />
      ) : null}

      {open?.kind === "node" ? (
        <TemplateNodeDialog
          config={config}
          stageIndex={open.stage}
          nodeIndex={open.node}
          skills={skills}
          agents={agents}
          refusal={refusal}
          editor={editor}
          onClose={close}
        />
      ) : null}
    </div>
  );
}
