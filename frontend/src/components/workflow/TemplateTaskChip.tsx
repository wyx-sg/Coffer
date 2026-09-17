// frontend/src/components/workflow/TemplateTaskChip.tsx
// One task on the map: a box with its name, the two things a reader scans a
// flow for — what kind of work it is, and whether it stops for a decision —
// and the one act that is about the BOX rather than about its contents.
//
// Deleting is that act, so it is here and not in the dialog. The dialog is
// where a task's fields are; a Delete inside it sits among them looking like
// another field, and the thing being deleted is the box you are looking at.
// The stage box already works this way, and the two should match.
//
// A button cannot nest inside a button, so the chip is the clickable surface
// and the bin is a sibling positioned over its corner.
import { ShieldQuestion, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { TemplateNode } from "@/lib/api/workflow";

interface Props {
  node: TemplateNode;
  onClick: () => void;
  onDelete: () => void;
  /** False for the last task in a stage: the contract's minimum is one node
   *  and the engine reads `stage.nodes[0]`, so the stage is what goes. */
  canDelete: boolean;
  disabled?: boolean;
}

export function TemplateTaskChip({ node, onClick, onDelete, canDelete, disabled = false }: Props) {
  const { t } = useTranslation();
  const label = node.name.length > 0 ? node.name : node.key;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onClick}
        data-testid={`task-${node.key}`}
        className="flex min-h-[3.5rem] min-w-[10rem] max-w-[16rem] flex-col items-start gap-1.5 rounded-md border border-border bg-background p-3 pr-10 text-left transition-colors hover:border-primary/50 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="w-full truncate text-sm font-medium">{label}</span>
        <span className="flex items-center gap-1.5">
          <Badge variant="outline">{t(`workflow.node.types.${node.type}`)}</Badge>
          {node.approval === "always" ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <ShieldQuestion className="size-3.5 text-muted-foreground" aria-hidden />
              </TooltipTrigger>
              <TooltipContent>{t("workflow.templates.approvals.always")}</TooltipContent>
            </Tooltip>
          ) : null}
        </span>
      </button>

      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={
              canDelete ? "absolute right-1 top-1" : "absolute right-1 top-1 cursor-not-allowed"
            }
          >
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-muted-foreground hover:text-destructive"
              disabled={!canDelete || disabled}
              aria-label={t("workflow.templates.removeNode", { name: label })}
              onClick={onDelete}
            >
              <Trash2 className="size-3.5" aria-hidden />
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          {canDelete
            ? t("workflow.templates.removeNode", { name: label })
            : t("workflow.templates.lastNode")}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
