// frontend/src/components/workflow/TemplateStageList.tsx
// The left half of the editor: the shared stage list, with the editor's own
// concerns hung off it.
//
// The picture itself is `StageRailList`, which a run draws too — a run is this
// template with state on it, and the two must not become two pictures of one
// thing. What is only the editor's lives here: each stage's own Edit and
// Delete, the refusal a save came back with, and the button that adds a stage.
//
// Every row carries its own pair, exactly as a task card does. One pair over
// the list, acting on whichever stage was selected, made selecting a stage a
// precondition for editing it — and sat close enough to the other pane to read
// as editing what that pane was showing.
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { StageRailList } from "@/components/workflow/StageRailList";
import type { TemplateConfig } from "@/lib/api/workflow";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  config: TemplateConfig;
  refusal: TemplateRefusal | null;
  /** Index of the stage whose tasks the other half is showing. */
  selected: number;
  onSelect: (index: number) => void;
  onAddStage: () => void;
  onEditStage: (index: number) => void;
  /** Asks to delete; the confirmation and the write are the caller's. */
  onDeleteStage: (index: number) => void;
  busy: boolean;
}

export function TemplateStageList({
  config,
  refusal,
  selected,
  onSelect,
  onAddStage,
  onEditStage,
  onDeleteStage,
  busy,
}: Props) {
  const { t } = useTranslation();
  // The last stage cannot go: a template with no stages is refused, and
  // deleting the template is the other menu.
  const last = config.stages.length === 1;

  return (
    <StageRailList
      stages={config.stages.map((stage, index) => {
        const label = stage.name.length > 0 ? stage.name : stage.key;
        return {
          key: stage.key,
          name: stage.name,
          optional: stage.optional,
          actions: (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label={t("workflow.templates.editStage", { name: label })}
                onClick={() => onEditStage(index)}
              >
                <Pencil className="mr-1 size-3.5" aria-hidden />
                {t("common.edit")}
              </Button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className={last ? "cursor-not-allowed" : undefined}>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="text-muted-foreground hover:text-destructive"
                      disabled={last || busy}
                      aria-label={t("workflow.templates.removeStage", { name: label })}
                      onClick={() => onDeleteStage(index)}
                    >
                      <Trash2 className="mr-1 size-3.5" aria-hidden />
                      {t("common.delete")}
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {last
                    ? t("workflow.templates.lastStage")
                    : t("workflow.templates.removeStage", { name: label })}
                </TooltipContent>
              </Tooltip>
            </>
          ),
        };
      })}
      selected={selected}
      onSelect={onSelect}
      footer={
        <div className="space-y-3">
          <TemplateFieldError refusal={refusal} path="stages" />
          <Button type="button" variant="outline" size="sm" className="w-full" onClick={onAddStage}>
            <Plus className="mr-1 size-3.5" aria-hidden />
            {t("workflow.templates.addStage")}
          </Button>
        </div>
      }
    />
  );
}
