// frontend/src/components/workflow/TemplateNodeFlow.tsx
// The second level of the map: one stage, and the tasks inside it in the order
// they run (FR-061).
//
// Down rather than across, and one per row: a stage's tasks are a sequence,
// and a row of chips reads as a set of options. The chevron between them is
// the same one the stage diagram uses, because it means the same thing.
//
// The stage's own fields are behind the pencil, exactly as at the level above.
// What is different here is that going back is a control: the reader drilled
// in, so they need the way out, and it names the level they came from rather
// than saying "Back".
import { ChevronDown, ChevronLeft, Pencil, Plus } from "lucide-react";
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplateTaskChip } from "@/components/workflow/TemplateTaskChip";
import type { TemplateStage } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import { removeNode } from "@/lib/workflow/templateDraft";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  stage: TemplateStage;
  index: number;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
  onBack: () => void;
  onEditStage: () => void;
  /** Open a task's fields; `null` adds one to this stage. */
  onEditNode: (nodeIndex: number | null) => void;
}

export function TemplateNodeFlow({
  stage,
  index,
  refusal,
  editor,
  onBack,
  onEditStage,
  onEditNode,
}: Props) {
  const { t } = useTranslation();
  const path = `stages[${index}]`;
  const label = stage.name.length > 0 ? stage.name : stage.key;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft className="mr-1 size-4" aria-hidden />
          {t("workflow.templates.backToStages")}
        </Button>
        <h3 className="font-serif text-lg">{label}</h3>
        {stage.optional ? (
          <Badge variant="secondary">{t("workflow.templates.optional")}</Badge>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={t("workflow.templates.editStage", { name: label })}
          onClick={onEditStage}
        >
          <Pencil className="size-4" aria-hidden />
        </Button>
      </div>

      <div className="flex flex-col items-start gap-1">
        {stage.nodes.map((node, nodeIndex) => (
          <Fragment key={node.key}>
            {nodeIndex > 0 ? (
              <ChevronDown className="ml-16 size-4 text-muted-foreground" aria-hidden />
            ) : null}
            <TemplateTaskChip
              node={node}
              onClick={() => onEditNode(nodeIndex)}
              canDelete={stage.nodes.length > 1}
              disabled={editor.isSaving}
              onDelete={() =>
                void editor.apply((c) => removeNode(c, index, nodeIndex)).catch(() => {})
              }
            />
          </Fragment>
        ))}
      </div>

      <TemplateFieldError refusal={refusal} path={`${path}.nodes`} />

      <Button type="button" variant="outline" onClick={() => onEditNode(null)}>
        <Plus className="mr-1 size-4" aria-hidden />
        {t("workflow.templates.addNode")}
      </Button>
    </div>
  );
}
