// frontend/src/components/workflow/TemplateFailurePolicy.tsx
// What the run does when this node fails: stop, carry on, or try again N times
// (data-model: `nodes[].on_failure.action`, with `times` >= 1 when `retry`).
//
// The count appears only for `retry`, because that is the only action it means
// anything for — and it is required there, so it is never left unset: switching
// to `retry` brings a 1 with it.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import type { TemplateOnFailure } from "@/lib/api/workflow";
import { FAILURE_ACTIONS } from "@/lib/workflow/templateDraft";
import { fieldErrorProps, type TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  id: string;
  /** JSON path of `on_failure`, e.g. `stages[0].nodes[1].on_failure`. */
  path: string;
  value: TemplateOnFailure;
  refusal: TemplateRefusal | null;
  onChange: (value: TemplateOnFailure) => void;
}

export function TemplateFailurePolicy({ id, path, value, refusal, onChange }: Props) {
  const { t } = useTranslation();
  const actionPath = `${path}.action`;
  const timesPath = `${path}.times`;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{t("workflow.templates.onFailure")}</Label>
      <div className="flex items-center gap-2">
        <Select
          value={value.action}
          onValueChange={(next) =>
            onChange(
              next === "retry"
                ? { action: "retry", times: value.times ?? 1 }
                : { action: next as TemplateOnFailure["action"] },
            )
          }
        >
          <SelectTrigger id={id} {...fieldErrorProps(refusal, actionPath)}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FAILURE_ACTIONS.map((action) => (
              <SelectItem key={action} value={action}>
                {t(`workflow.templates.failure.${action}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {value.action === "retry" ? (
          <Input
            type="number"
            min={1}
            className="w-20"
            aria-label={t("workflow.templates.retryTimes")}
            value={value.times ?? 1}
            onChange={(e) => onChange({ action: "retry", times: Number(e.target.value) })}
            {...fieldErrorProps(refusal, timesPath)}
          />
        ) : null}
      </div>
      <TemplateFieldError refusal={refusal} path={actionPath} />
      <TemplateFieldError refusal={refusal} path={timesPath} />
      <TemplateFieldError refusal={refusal} path={path} />
    </div>
  );
}
