// frontend/src/components/workflow/TemplateSendBack.tsx
// Where a stage sends work back to when something later says an earlier stage
// has to be redone (FR-025), edited inside that stage's own dialog.
//
// Split out of `TemplateStageDialog` so that file stays within its size
// budget, and it splits cleanly because it is the one part of a stage that is
// about OTHER stages: a reason the developer names, and an earlier stage to
// land on. Everything else in that dialog is about the stage itself.
//
// Only earlier stages are offered. A forward edge is the array order and is
// never written (FR-005) — the editor has no way to draw one, and the daemon
// refuses one if it ever arrives.
//
// Each route carries its OWN ceiling (FR-026). The work a route creates is an
// ad-hoc task that exists nowhere else in the template, so the route is that
// task's declaration and the only place its limit can be written — and a
// review that may send work back three times is a different judgement from a
// task that may be tried three times.
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TemplateStage } from "@/lib/api/workflow";
import { DEFAULT_ATTEMPT_CEILING, type StageValues } from "@/lib/workflow/templateDraft";

interface Props {
  /** The stages this one may send work back to: strictly earlier ones. */
  targets: TemplateStage[];
  value: StageValues["sendBack"];
  onChange: (next: StageValues["sendBack"]) => void;
  /** The stage's name, for the remove button's label. */
  stageName: string;
}

export function TemplateSendBack({ targets, value, onChange, stageName }: Props) {
  const { t } = useTranslation();
  // The first stage has nothing behind it, so there is nothing to offer.
  if (targets.length === 0) return null;

  return (
    <div className="space-y-2">
      <Label>{t("workflow.templates.sendBack")}</Label>
      <p className="text-xs text-muted-foreground">{t("workflow.templates.sendBackHint")}</p>
      {value.map((row, i) => (
        <div key={i} className="flex items-end gap-2">
          <div className="flex-1 space-y-1">
            <Label htmlFor={`send-back-reason-${i}`} className="text-xs">
              {t("workflow.templates.edgeReason")}
            </Label>
            <Input
              id={`send-back-reason-${i}`}
              value={row.reason}
              placeholder={t("workflow.templates.edgeReasonPlaceholder")}
              onChange={(e) =>
                onChange(value.map((r, j) => (j === i ? { ...r, reason: e.target.value } : r)))
              }
            />
          </div>
          <div className="flex-1 space-y-1">
            <Label htmlFor={`send-back-to-${i}`} className="text-xs">
              {t("workflow.templates.edgeTo")}
            </Label>
            <Select
              value={row.to_stage}
              onValueChange={(to_stage) =>
                onChange(value.map((r, j) => (j === i ? { ...r, to_stage } : r)))
              }
            >
              <SelectTrigger id={`send-back-to-${i}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {targets.map((stage) => (
                  <SelectItem key={stage.key} value={stage.key}>
                    {stage.name || stage.key}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-24 space-y-1">
            <Label htmlFor={`send-back-ceiling-${i}`} className="text-xs">
              {t("workflow.templates.attemptCeiling")}
            </Label>
            <Input
              id={`send-back-ceiling-${i}`}
              type="number"
              min={1}
              value={row.attempt_ceiling}
              onChange={(e) =>
                onChange(
                  value.map((r, j) =>
                    j === i
                      ? { ...r, attempt_ceiling: Number(e.target.value) || DEFAULT_ATTEMPT_CEILING }
                      : r,
                  ),
                )
              }
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-destructive"
            aria-label={t("workflow.templates.removeEdge", {
              from: stageName,
              to: row.to_stage,
            })}
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() =>
          onChange([
            ...value,
            {
              reason: "",
              to_stage: targets[targets.length - 1].key,
              attempt_ceiling: DEFAULT_ATTEMPT_CEILING,
            },
          ])
        }
      >
        <Plus className="mr-1 size-3.5" aria-hidden />
        {t("workflow.templates.addEdge")}
      </Button>
    </div>
  );
}
