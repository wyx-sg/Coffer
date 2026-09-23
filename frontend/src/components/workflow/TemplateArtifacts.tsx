// frontend/src/components/workflow/TemplateArtifacts.tsx
// What a node OWES: the files it must leave behind, and which of them block
// its completion when they were never written.
//
// A name here is one path segment — no separators, no dots-only (data-model).
// The editor does not pre-validate it into silence: the daemon owns that rule
// and names the field when it refuses, and a second copy of the rule in the
// browser is a second rule to drift.
import { Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import type { TemplateArtifact } from "@/lib/api/workflow";
import { fieldErrorProps, type TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  artifacts: TemplateArtifact[];
  /** JSON path of the artifact array, e.g. `stages[0].nodes[1].artifacts`. */
  path: string;
  refusal: TemplateRefusal | null;
  onChange: (artifacts: TemplateArtifact[]) => void;
}

export function TemplateArtifacts({ artifacts, path, refusal, onChange }: Props) {
  const { t } = useTranslation();

  const patch = (index: number, next: Partial<TemplateArtifact>) =>
    onChange(artifacts.map((a, i) => (i === index ? { ...a, ...next } : a)));

  return (
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">
        {t("workflow.templates.artifacts")}
      </Label>
      {artifacts.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("workflow.templates.noArtifacts")}</p>
      ) : null}
      {artifacts.map((artifact, index) => {
        const namePath = `${path}[${index}].name`;
        return (
          <div key={index} className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Input
                className="w-56"
                aria-label={t("workflow.templates.artifactName", { index: index + 1 })}
                value={artifact.name}
                onChange={(e) => patch(index, { name: e.target.value })}
                placeholder={t("workflow.templates.artifactPlaceholder")}
                {...fieldErrorProps(refusal, namePath)}
              />
              <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Checkbox
                  checked={artifact.required ?? true}
                  onChange={(e) => patch(index, { required: e.target.checked })}
                />
                {t("workflow.templates.artifactRequired")}
              </label>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("workflow.templates.removeArtifact", { name: artifact.name })}
                onClick={() => onChange(artifacts.filter((_, i) => i !== index))}
              >
                <X className="size-4" aria-hidden />
              </Button>
            </div>
            <TemplateFieldError refusal={refusal} path={namePath} />
          </div>
        );
      })}
      <TemplateFieldError refusal={refusal} path={path} />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...artifacts, { name: "", required: true }])}
      >
        <Plus className="mr-1 size-3.5" aria-hidden />
        {t("workflow.templates.addArtifact")}
      </Button>
    </div>
  );
}
