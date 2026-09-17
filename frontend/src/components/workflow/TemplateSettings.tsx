// frontend/src/components/workflow/TemplateSettings.tsx
// The run-level fields: what this flow is for, how many attempts any one task
// gets across a run (FR-026), and the token budget whose exhaustion pauses the
// run rather than starting the next task (FR-018).
//
// These are three fields rather than a dialog's worth, so they are edited in
// place and WRITTEN ON BLUR — the page has no Save button (FR-062) and a write
// per keystroke would be a PATCH per letter typed. Blur is the moment the
// developer has finished with a field.
//
// The description is the RESOURCE's description as well as the config's, and
// `useTemplateEditor` writes it on both halves of the same PATCH: a template
// whose list row says one thing and whose config says another has two
// descriptions.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import type { TemplateConfig } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import { fieldErrorProps, type TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  config: TemplateConfig;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
}

/** An empty number field means "unset", not zero: `token_budget` is nullable
 *  and an `attempt_ceiling` of 0 would be refused. */
function numberOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  return trimmed.length === 0 ? null : Number(trimmed);
}

export function TemplateSettings({ config, refusal, editor }: Props) {
  const { t } = useTranslation();
  // What is being typed, until the field is left. The server's value is the
  // source of truth the moment it changes underneath — a save landing, or a
  // template arriving over sync.
  const [description, setDescription] = useState(config.description ?? "");
  const [ceiling, setCeiling] = useState(String(config.attempt_ceiling ?? ""));
  const [budget, setBudget] = useState(String(config.token_budget ?? ""));

  useEffect(() => setDescription(config.description ?? ""), [config.description]);
  useEffect(() => setCeiling(String(config.attempt_ceiling ?? "")), [config.attempt_ceiling]);
  useEffect(() => setBudget(String(config.token_budget ?? "")), [config.token_budget]);

  const commit = (patch: Partial<TemplateConfig>) =>
    void editor.apply((current) => ({ ...current, ...patch })).catch(() => {});

  return (
    <Card className="paper-card">
      <CardHeader>
        <CardTitle className="font-serif">{t("workflow.templates.settings")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="template-description">{t("workflow.templates.description")}</Label>
          <Textarea
            id="template-description"
            rows={2}
            value={description}
            placeholder={t("workflow.templates.descriptionPlaceholder")}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => commit({ description: description.length > 0 ? description : null })}
            {...fieldErrorProps(refusal, "description")}
          />
          <TemplateFieldError refusal={refusal} path="description" />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="template-ceiling">{t("workflow.templates.attemptCeiling")}</Label>
            <Input
              id="template-ceiling"
              type="number"
              min={1}
              value={ceiling}
              onChange={(e) => setCeiling(e.target.value)}
              onBlur={() => commit({ attempt_ceiling: numberOrNull(ceiling) ?? undefined })}
              {...fieldErrorProps(refusal, "attempt_ceiling")}
            />
            <p className="text-xs text-muted-foreground">
              {t("workflow.templates.attemptCeilingHint")}
            </p>
            <TemplateFieldError refusal={refusal} path="attempt_ceiling" />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="template-budget">{t("workflow.templates.tokenBudget")}</Label>
            <Input
              id="template-budget"
              type="number"
              min={1}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              onBlur={() => commit({ token_budget: numberOrNull(budget) })}
              {...fieldErrorProps(refusal, "token_budget")}
            />
            <p className="text-xs text-muted-foreground">
              {t("workflow.templates.tokenBudgetHint")}
            </p>
            <TemplateFieldError refusal={refusal} path="token_budget" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
