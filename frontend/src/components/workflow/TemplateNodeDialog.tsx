// frontend/src/components/workflow/TemplateNodeDialog.tsx
// One task, in full: what it is called, what kind of work it is, what it runs,
// what it owes, what happens when it fails, and who runs it.
//
// This is where every field a task has now lives, and ONLY its fields. On the
// map a task is a box with a name and a type; opening it is how you see the
// rest, and Save inside this dialog is the only thing that writes it — there
// is no page-level save to forget to press.
//
// Deleting is not here. It is an act on the box rather than a field of it, so
// it lives on the box, beside the stage's own bin — a Delete sitting among
// eight fields reads like a ninth.
//
// The task's KEY is not asked for and not shown: it is a slug of the
// name, made unique across the template, recomputed on save. Nothing in the
// template points at a node key, so unlike a stage there is nothing to rewrite.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { TemplateArtifacts } from "@/components/workflow/TemplateArtifacts";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplateNodeFields } from "@/components/workflow/TemplateNodeFields";
import { TemplatePositionField } from "@/components/workflow/TemplatePositionField";
import { translateApiError } from "@/lib/api/errors";
import type { TemplateConfig } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import {
  addNode,
  blankNode,
  moveNode,
  nodeValues,
  saveNode,
  type NodeValues,
} from "@/lib/workflow/templateDraft";
import { fieldErrorProps, type TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  config: TemplateConfig;
  stageIndex: number;
  /** `null` for a task that does not exist yet. */
  nodeIndex: number | null;
  skills: string[];
  agents: string[];
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
  onClose: () => void;
}

export function TemplateNodeDialog({
  config,
  stageIndex,
  nodeIndex,
  skills,
  agents,
  refusal,
  editor,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const stage = config.stages[stageIndex];
  const existing = nodeIndex === null ? undefined : stage?.nodes[nodeIndex];
  // The key is the one field of a node this dialog does not hold: it is
  // derived from the name on save, so carrying it here would be
  // carrying a value nothing reads.
  const [values, setValues] = useState<NodeValues>(() =>
    existing === undefined ? blankNode() : nodeValues(existing),
  );

  // A new task goes on the end of its stage and has nowhere else to be.
  const [position, setPosition] = useState(nodeIndex ?? stage?.nodes.length ?? 0);

  const path =
    nodeIndex === null
      ? `stages[${stageIndex}].nodes`
      : `stages[${stageIndex}].nodes[${nodeIndex}]`;
  const id = "task";
  const incomplete = values.name.trim().length === 0;

  const patch = (next: Partial<NodeValues>) => setValues((current) => ({ ...current, ...next }));

  const write = (edit: (config: TemplateConfig) => TemplateConfig) =>
    void editor
      .apply(edit)
      .then(onClose)
      // The refusal is rendered below; the dialog stays open on it.
      .catch(() => {});

  const submit = () => {
    const trimmed = { ...values, name: values.name.trim() };
    write((c) => {
      if (nodeIndex === null) return addNode(c, stageIndex, trimmed);
      const saved = saveNode(c, stageIndex, nodeIndex, trimmed);
      return moveNode(saved, stageIndex, nodeIndex, position - nodeIndex);
    });
  };

  return (
    <Dialog open onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {nodeIndex === null
              ? t("workflow.templates.addNode")
              : t("workflow.templates.editNodeTitle")}
          </DialogTitle>
          <DialogDescription>
            {t("workflow.templates.nodeDescription", { stage: stage?.name || "" })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={`${id}-name`}>{t("workflow.templates.nodeName")}</Label>
            <Input
              id={`${id}-name`}
              value={values.name}
              placeholder={t("workflow.templates.nodeNamePlaceholder")}
              onChange={(e) => patch({ name: e.target.value })}
              {...fieldErrorProps(refusal, `${path}.name`)}
            />
            <TemplateFieldError refusal={refusal} path={`${path}.name`} />
          </div>

          {nodeIndex === null ? null : (
            <TemplatePositionField
              id="task-position"
              value={position}
              count={stage?.nodes.length ?? 0}
              onChange={setPosition}
              label={t("workflow.templates.nodePosition")}
              hint={t("workflow.templates.nodePositionHint")}
              disabled={editor.isSaving}
            />
          )}

          <TemplateNodeFields
            id={id}
            path={path}
            values={values}
            skills={skills}
            agents={agents}
            refusal={refusal}
            patch={patch}
          />

          <div className="space-y-1.5">
            <Label htmlFor={`${id}-instructions`}>{t("workflow.templates.instructions")}</Label>
            <Textarea
              id={`${id}-instructions`}
              rows={3}
              value={values.instructions ?? ""}
              placeholder={t("workflow.templates.instructionsPlaceholder")}
              onChange={(e) =>
                patch({ instructions: e.target.value.length > 0 ? e.target.value : null })
              }
              {...fieldErrorProps(refusal, `${path}.instructions`)}
            />
            <TemplateFieldError refusal={refusal} path={`${path}.instructions`} />
          </div>

          <TemplateArtifacts
            artifacts={values.artifacts ?? []}
            path={`${path}.artifacts`}
            refusal={refusal}
            onChange={(artifacts) => patch({ artifacts })}
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
