// frontend/src/components/workflow/TemplateStageBox.tsx
// One stage on the map: its name, where it sits in the order, the tasks in it
// as small boxes, and the feedback edges leaving it as return arrows.
//
// Nothing here is a form. The box shows what a reader scanning the flow needs
// — what this stage is called, what it does, whether it may be skipped — and
// every field is behind the click that opens the thing's own dialog.
//
// "Where it sits" is not a control on this box. The order IS the forward
// path (FR-005), so moving a stage is an edit to the flow — and every other
// edit to a stage is made in the stage's dialog, so this one is too. The box
// keeps only what a reader scanning the flow needs, plus the two acts that
// are about the box itself rather than about its contents: open it, bin it.
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplateTaskChip } from "@/components/workflow/TemplateTaskChip";
import type { TemplateConfig, TemplateStage } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import { removeNode, removeStage } from "@/lib/workflow/templateDraft";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  config: TemplateConfig;
  stage: TemplateStage;
  index: number;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
  onEditStage: () => void;
  /** `null` opens the dialog on a NEW task in this stage. */
  onEditNode: (nodeIndex: number | null) => void;
}

export function TemplateStageBox({
  config,
  stage,
  index,
  refusal,
  editor,
  onEditStage,
  onEditNode,
}: Props) {
  const { t } = useTranslation();
  const path = `stages[${index}]`;
  const label = stage.name.length > 0 ? stage.name : stage.key;
  const stageCount = config.stages.length;

  return (
    <Card className="paper-card">
      <CardHeader className="flex flex-row flex-wrap items-center gap-2 space-y-0 pb-3">
        <span className="text-sm text-muted-foreground">{index + 1}</span>
        <button
          type="button"
          className="rounded-sm text-left font-serif text-lg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={onEditStage}
        >
          {label}
        </button>
        {stage.optional ? (
          <Badge variant="secondary">{t("workflow.templates.optional")}</Badge>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={t("workflow.templates.editStage", { name: label })}
            onClick={onEditStage}
          >
            <Pencil className="size-4" aria-hidden />
          </Button>
          {/* The last stage cannot go: a template with no stages is refused,
              and deleting the template is the other menu. */}
          <Tooltip>
            <TooltipTrigger asChild>
              <span className={stageCount === 1 ? "cursor-not-allowed" : undefined}>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-destructive"
                  disabled={stageCount === 1 || editor.isSaving}
                  aria-label={t("workflow.templates.removeStage", { name: label })}
                  onClick={() => void editor.apply((c) => removeStage(c, index)).catch(() => {})}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {stageCount === 1
                ? t("workflow.templates.lastStage")
                : t("workflow.templates.removeStage", { name: label })}
            </TooltipContent>
          </Tooltip>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {stage.nodes.map((node, nodeIndex) => (
            <TemplateTaskChip
              key={node.key}
              node={node}
              onClick={() => onEditNode(nodeIndex)}
              canDelete={stage.nodes.length > 1}
              disabled={editor.isSaving}
              onDelete={() =>
                void editor.apply((c) => removeNode(c, index, nodeIndex)).catch(() => {})
              }
            />
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-auto min-h-[3.5rem] border-dashed"
            onClick={() => onEditNode(null)}
          >
            <Plus className="mr-1 size-3.5" aria-hidden />
            {t("workflow.templates.addNode")}
          </Button>
        </div>

        <TemplateFieldError refusal={refusal} path={`${path}.nodes`} />
        <TemplateFieldError refusal={refusal} path={path} />
      </CardContent>
    </Card>
  );
}
