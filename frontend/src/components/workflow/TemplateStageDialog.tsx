// frontend/src/components/workflow/TemplateStageDialog.tsx
// A stage's own fields: what it is called, whether it may be skipped, and
// where in the order it runs.
//
// There is nothing here about sending work back, because a workflow draws no
// route between stages (FR-025): a finding in a later task is acted on by the
// developer who is holding it, by retrying the task that was wrong or adding
// one that fixes it, and neither is a decision a template can make in advance.
//
// The stage's KEY is not asked for and not shown (FR-060): it is derived from
// the name on save.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplatePositionField } from "@/components/workflow/TemplatePositionField";
import { translateApiError } from "@/lib/api/errors";
import type { TemplateConfig } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import { addStage, moveStage, saveStage, type StageValues } from "@/lib/workflow/templateDraft";
import { fieldErrorProps, type TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  config: TemplateConfig;
  /** `null` for a stage that does not exist yet. */
  index: number | null;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
  onClose: () => void;
}

export function TemplateStageDialog({ config, index, refusal, editor, onClose }: Props) {
  const { t } = useTranslation();
  const existing = index === null ? undefined : config.stages[index];
  const [values, setValues] = useState<StageValues>({
    name: existing?.name ?? "",
    optional: existing?.optional ?? false,
  });
  // A new stage goes on the end and has nowhere else to be until it exists.
  const [position, setPosition] = useState(index ?? config.stages.length);

  const path = index === null ? "stages" : `stages[${index}]`;
  const incomplete = values.name.trim().length === 0;

  const patch = (next: Partial<StageValues>) => setValues((current) => ({ ...current, ...next }));

  const submit = () => {
    const trimmed = { ...values, name: values.name.trim() };
    void editor
      .apply((c) => {
        if (index === null) return addStage(c, trimmed);
        // Saved, then moved: `saveStage` re-derives the key at the old index,
        // which keeps the two edits from having to agree about where the stage
        // is.
        const saved = saveStage(c, index, trimmed);
        return moveStage(saved, index, position - index);
      })
      .then(onClose)
      // The refusal is already rendered below; the dialog stays open on it so
      // what was typed is still there to correct.
      .catch(() => {});
  };

  return (
    <Dialog open onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {index === null
              ? t("workflow.templates.addStage")
              : t("workflow.templates.editStageTitle")}
          </DialogTitle>
          <DialogDescription>
            {index === null
              ? t("workflow.templates.addStageDescription")
              : t("workflow.templates.editStageDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="stage-name">{t("workflow.templates.stageName")}</Label>
            <Input
              id="stage-name"
              value={values.name}
              placeholder={t("workflow.templates.stageNamePlaceholder")}
              onChange={(e) => patch({ name: e.target.value })}
              {...fieldErrorProps(refusal, `${path}.name`)}
            />
            <TemplateFieldError refusal={refusal} path={`${path}.name`} />
          </div>

          {index === null ? null : (
            <TemplatePositionField
              id="stage-position"
              value={position}
              count={config.stages.length}
              onChange={setPosition}
              label={t("workflow.templates.stagePosition")}
              hint={t("workflow.templates.stagePositionHint")}
              disabled={editor.isSaving}
            />
          )}

          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              className="mt-0.5"
              checked={values.optional}
              onChange={(e) => patch({ optional: e.target.checked })}
            />
            <span>
              {t("workflow.templates.optional")}
              <span className="block text-xs text-muted-foreground">
                {t("workflow.templates.optionalHint")}
              </span>
            </span>
          </label>

          {editor.error && refusal === null ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, editor.error)}
            </p>
          ) : null}
          <TemplateFieldError refusal={refusal} path={path} />
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={incomplete || editor.isSaving} onClick={submit}>
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
