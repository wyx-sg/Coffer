// frontend/src/components/workflow/TemplateTaskCard.tsx
// One task in the stage's panel, saying what it actually DOES.
//
// It used to be a chip: a name and a type badge. That is enough to know a task
// is there and nothing else, so the panel holding four of them was mostly
// empty and every question about any of them — what does it run, what does it
// owe, does it stop for approval, what happens when it fails — cost a dialog.
// The fields are the template; a card that hid all of them was a list of
// headings.
//
// So the card states them, read-only, and the dialog stays the place they are
// CHANGED. Nothing is invented for a field that is not set: a task with no
// skill, no artifacts and the default failure behaviour says one line, which
// is honest and still taller than a chip.
//
// THE WHOLE CARD OPENS IT. A card that looks like a thing and answers only to
// a small button in its corner teaches the developer to aim; the Edit button
// stays because it says what clicking does and because Delete beside it would
// otherwise stand alone. Delete stops the click from reaching the card, which
// is the one place the two would disagree.
import { Pencil, ShieldQuestion, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { TemplateNode } from "@/lib/api/workflow";

interface Props {
  node: TemplateNode;
  onEdit: () => void;
  onDelete: () => void;
  /** False for the last task in a stage: the contract's minimum is one node
   *  and the engine reads `stage.nodes[0]`, so the stage is what goes. */
  canDelete: boolean;
  disabled?: boolean;
}

export function TemplateTaskCard({ node, onEdit, onDelete, canDelete, disabled = false }: Props) {
  const { t } = useTranslation();
  const label = node.name.length > 0 ? node.name : node.key;
  const required = (node.artifacts ?? []).filter((a) => a.required).map((a) => a.name);
  const optional = (node.artifacts ?? []).filter((a) => !a.required).map((a) => a.name);

  return (
    <div
      data-testid={`task-${node.key}`}
      role="button"
      tabIndex={0}
      aria-label={t("workflow.templates.editNode", { name: label })}
      onClick={onEdit}
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        onEdit();
      }}
      className="w-full cursor-pointer space-y-2 rounded-md border border-border bg-background p-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{label}</span>
        <Badge variant="outline" className="shrink-0">
          {t(`workflow.node.types.${node.type}`)}
        </Badge>
        {node.approval === "always" ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="secondary" className="shrink-0 gap-1">
                <ShieldQuestion className="size-3" aria-hidden />
                {t("workflow.templates.approvals.always")}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>{t("workflow.templates.approval")}</TooltipContent>
          </Tooltip>
        ) : null}
      </div>

      <dl className="space-y-0.5 text-xs text-muted-foreground">
        <Line label={t("workflow.templates.skill")} value={node.skill} />
        <Line label={t("workflow.templates.agent")} value={node.agent} />
        <Line
          label={t("workflow.templates.artifacts")}
          value={
            required.length + optional.length === 0
              ? null
              : [
                  ...required.map(
                    (name) => `${name}（${t("workflow.templates.artifactRequired")}）`,
                  ),
                  ...optional,
                ].join("、")
          }
        />
        <Line
          label={t("workflow.templates.onFailure")}
          value={
            node.on_failure?.action === "retry"
              ? `${t("workflow.templates.failure.retry")} × ${node.on_failure.times ?? 1}`
              : t(`workflow.templates.failure.${node.on_failure?.action ?? "stop"}`)
          }
        />
      </dl>

      {node.instructions ? (
        <p className="line-clamp-2 text-xs text-muted-foreground">{node.instructions}</p>
      ) : null}

      <div className="flex items-center gap-2 pt-1">
        {/* The card behind it already opens the dialog; letting the click
            through would open it twice for one press. */}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            onEdit();
          }}
        >
          <Pencil className="mr-1 size-3.5" aria-hidden />
          {t("common.edit")}
        </Button>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={canDelete ? undefined : "cursor-not-allowed"}>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                disabled={!canDelete || disabled}
                aria-label={t("workflow.templates.removeNode", { name: label })}
                // Deleting must not also open what it is deleting.
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
              >
                <Trash2 className="mr-1 size-3.5" aria-hidden />
                {t("common.delete")}
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
    </div>
  );
}

/** One field, or nothing at all. A row reading "Skill: none" is a row spent
 *  saying that a thing the template does not use is not used. */
function Line({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex gap-1.5">
      <dt className="shrink-0">{label}</dt>
      <dd className="min-w-0 flex-1 truncate text-foreground/80">{value}</dd>
    </div>
  );
}
