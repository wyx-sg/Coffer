// frontend/src/components/workflow/TemplateStageCard.tsx
// One stage at the top level of the map: what it is called, whether it may be
// skipped, and how much work is in it — and nothing about that work itself.
//
// The card is a way IN, not a form. Clicking it opens the stage's own diagram
// (FR-061); the pencil opens its fields; the bin removes it. Three acts, three
// targets, and the reader scanning the flow is shown the shape rather than
// forty controls belonging to tasks they have not asked about yet.
import { ChevronRight, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import type { TemplateStage } from "@/lib/api/workflow";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  stage: TemplateStage;
  index: number;
  /** False for the last stage: a template with none is refused. */
  canDelete: boolean;
  busy: boolean;
  refusal: TemplateRefusal | null;
  onOpen: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export function TemplateStageCard({
  stage,
  index,
  canDelete,
  busy,
  refusal,
  onOpen,
  onEdit,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const path = `stages[${index}]`;
  const label = stage.name.length > 0 ? stage.name : stage.key;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onOpen}
        data-testid={`stage-${stage.key}`}
        aria-label={t("workflow.templates.openStage", { name: label })}
        className="paper-card flex w-full items-center gap-3 rounded-lg border border-border bg-card p-4 pr-28 text-left transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="text-sm text-muted-foreground">{index + 1}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-serif text-lg">{label}</span>
          <span className="text-sm text-muted-foreground">
            {t("workflow.templates.taskCount", { count: stage.nodes.length })}
          </span>
        </span>
        {stage.optional ? (
          <Badge variant="secondary">{t("workflow.templates.optional")}</Badge>
        ) : null}
      </button>

      {/* Siblings, not children: a button cannot nest inside a button. On the
          card's own centre line, so the three things on the right — edit, bin,
          and the chevron that says the card opens — read as one row. */}
      <div className="absolute right-4 top-1/2 flex -translate-y-1/2 items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={t("workflow.templates.editStage", { name: label })}
          onClick={onEdit}
        >
          <Pencil className="size-4" aria-hidden />
        </Button>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={canDelete ? undefined : "cursor-not-allowed"}>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground hover:text-destructive"
                disabled={!canDelete || busy}
                aria-label={t("workflow.templates.removeStage", { name: label })}
                onClick={onDelete}
              >
                <Trash2 className="size-4" aria-hidden />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {canDelete
              ? t("workflow.templates.removeStage", { name: label })
              : t("workflow.templates.lastStage")}
          </TooltipContent>
        </Tooltip>
        {/* Last, and outside the button it belongs to: it is the mark that
            this card opens, and a mark that sat left of the edit and the bin
            would read as pointing at them. */}
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </div>

      <TemplateFieldError refusal={refusal} path={`${path}.nodes`} />
      <TemplateFieldError refusal={refusal} path={path} />
    </div>
  );
}
