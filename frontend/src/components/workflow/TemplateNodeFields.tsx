// frontend/src/components/workflow/TemplateNodeFields.tsx
// The paired choices a task makes — what kind of work it is, what skill drives
// it, whether it stops for a decision, what happens when it fails, who runs it
// and how many tries it gets — kept apart from the dialog so that file stays
// within its size budget.
//
// A grid rather than a list because they pair up: type with skill (what it
// does and what it reads to do it), approval with failure (the two ways it
// stops), and the agent with the ceiling (who runs it, how many times).
//
// The CEILING is here rather than on the workflow because it is a fact about
// this task. One number for the whole flow made the drafting task that is
// cheap to re-run and the deploy task that must not be tried twice share a
// limit that was wrong for one of them.
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
import { TemplateFailurePolicy } from "@/components/workflow/TemplateFailurePolicy";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplateResourcePicker } from "@/components/workflow/TemplateResourcePicker";
import {
  APPROVALS,
  DEFAULT_ATTEMPT_CEILING,
  NODE_TYPES,
  type NodeValues,
} from "@/lib/workflow/templateDraft";
import { fieldErrorProps, type TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  id: string;
  /** JSON path of the node itself, which every field hangs off. */
  path: string;
  values: NodeValues;
  skills: string[];
  agents: string[];
  refusal: TemplateRefusal | null;
  patch: (next: Partial<NodeValues>) => void;
}

export function TemplateNodeFields({ id, path, values, skills, agents, refusal, patch }: Props) {
  const { t } = useTranslation();

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-type`}>{t("workflow.templates.nodeType")}</Label>
        <Select
          value={values.type}
          onValueChange={(next) => patch({ type: next as NodeValues["type"] })}
        >
          <SelectTrigger id={`${id}-type`} {...fieldErrorProps(refusal, `${path}.type`)}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {NODE_TYPES.map((type) => (
              <SelectItem key={type} value={type}>
                {t(`workflow.node.types.${type}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <TemplateFieldError refusal={refusal} path={`${path}.type`} />
      </div>

      <TemplateResourcePicker
        id={`${id}-skill`}
        label={t("workflow.templates.skill")}
        options={skills}
        value={values.skill ?? null}
        onChange={(skill) => patch({ skill })}
        noneLabel={t("workflow.templates.noSkill")}
        path={`${path}.skill`}
        refusal={refusal}
      />

      <div className="space-y-1.5">
        <Label htmlFor={`${id}-approval`}>{t("workflow.templates.approval")}</Label>
        <Select
          value={values.approval ?? "never"}
          onValueChange={(next) => patch({ approval: next as NodeValues["approval"] })}
        >
          <SelectTrigger id={`${id}-approval`} {...fieldErrorProps(refusal, `${path}.approval`)}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {APPROVALS.map((approval) => (
              <SelectItem key={approval} value={approval}>
                {t(`workflow.templates.approvals.${approval}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <TemplateFieldError refusal={refusal} path={`${path}.approval`} />
      </div>

      <TemplateFailurePolicy
        id={`${id}-failure`}
        path={`${path}.on_failure`}
        value={values.on_failure ?? { action: "stop" }}
        refusal={refusal}
        onChange={(on_failure) => patch({ on_failure })}
      />

      <TemplateResourcePicker
        id={`${id}-agent`}
        label={t("workflow.templates.agent")}
        options={agents}
        value={values.agent ?? null}
        onChange={(agent) => patch({ agent })}
        noneLabel={t("workflow.templates.defaultAgent")}
        path={`${path}.agent`}
        refusal={refusal}
      />

      <div className="space-y-1.5">
        <Label htmlFor={`${id}-ceiling`}>{t("workflow.templates.attemptCeiling")}</Label>
        <Input
          id={`${id}-ceiling`}
          type="number"
          min={1}
          value={values.attempt_ceiling ?? DEFAULT_ATTEMPT_CEILING}
          // An emptied box is the default rather than zero: there is no "no
          // ceiling", and a task allowed zero attempts could never run.
          onChange={(e) =>
            patch({ attempt_ceiling: Number(e.target.value) || DEFAULT_ATTEMPT_CEILING })
          }
          {...fieldErrorProps(refusal, `${path}.attempt_ceiling`)}
        />
        <p className="text-xs text-muted-foreground">
          {t("workflow.templates.attemptCeilingHint")}
        </p>
        <TemplateFieldError refusal={refusal} path={`${path}.attempt_ceiling`} />
      </div>
    </div>
  );
}
