// frontend/src/components/workflow/TemplateStageDialog.tsx
// A stage's own fields: what it is called, whether it may be skipped, and
// where it sends work back to when something later says it has to (FR-025).
//
// The feedback edges are HERE rather than in a tab of their own. An edge
// belongs to the stage it leaves — "testing sends work back to coding" is a
// fact about testing — and a tab listing every edge in the template made the
// developer hold the whole graph in their head to read one line of it.
//
// The stage's KEY is not asked for and not shown (FR-060): it is derived from
// the name on save, and the edges that named the old one are rewritten in the
// same edit.
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
import { TemplateSendBack } from "@/components/workflow/TemplateSendBack";
import { translateApiError } from "@/lib/api/errors";
import type { TemplateConfig } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import {
  addStage,
  earlierStages,
  moveStage,
  saveStage,
  sendBackOf,
  type StageValues,
} from "@/lib/workflow/templateDraft";
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
    sendBack: existing === undefined ? [] : sendBackOf(config, existing.key),
  });
  // A new stage goes on the end and has nowhere else to be until it exists.
  const [position, setPosition] = useState(index ?? config.stages.length);

  const path = index === null ? "stages" : `stages[${index}]`;
  // A new stage goes on the end, so what it may send back to is every stage
  // there is; an existing one may only point at the stages before it (FR-005).
  const targets = earlierStages(config, index ?? config.stages.length);
  const incomplete = values.name.trim().length === 0;

  const patch = (next: Partial<StageValues>) => setValues((current) => ({ ...current, ...next }));

  const submit = () => {
    const trimmed = { ...values, name: values.name.trim() };
    void editor
      .apply((c) => {
        if (index === null) return addStage(c, trimmed);
        // Saved, then moved: `saveStage` re-derives the key and rewrites the
        // edges that named it, and doing that at the old index keeps the two
        // edits from having to agree about where the stage is.
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

          <TemplateSendBack
            targets={targets}
            value={values.sendBack}
            onChange={(sendBack) => patch({ sendBack })}
            stageName={values.name}
          />

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
