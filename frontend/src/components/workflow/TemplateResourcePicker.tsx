// frontend/src/components/workflow/TemplateResourcePicker.tsx
// The skill and agent pickers — a node binds a REGISTERED thing, not a string
// somebody typed (data-model: `nodes[].skill` is the name of a registered
// skill resource, `nodes[].agent` an agent inside the template's scope).
//
// A value the vault no longer has does NOT vanish from the list. A picker that
// silently drops it would leave the developer looking at a blank field with no
// idea that the template still names a skill that was deleted, and the save
// would be refused by a server they cannot see. So a stale value is offered as
// what it is — still selected, marked gone, and replaceable.
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { fieldErrorProps, type TemplateRefusal } from "@/lib/workflow/templateErrors";

/** Radix forbids an empty option value, so "nothing chosen" needs a token. */
const NONE = "__none__";

interface Props {
  id: string;
  label: string;
  /** The registered names this picker offers. */
  options: string[];
  value: string | null;
  onChange: (value: string | null) => void;
  /** What `null` reads as — "No skill", "The run's default agent". */
  noneLabel: string;
  /** This field's JSON path, for the refusal that may name it (FR-055). */
  path: string;
  refusal: TemplateRefusal | null;
}

export function TemplateResourcePicker({
  id,
  label,
  options,
  value,
  onChange,
  noneLabel,
  path,
  refusal,
}: Props) {
  const { t } = useTranslation();
  const stale = value !== null && !options.includes(value);

  return (
    <div className="space-y-1.5">
      {/* The flex lives INSIDE the label, not on it. A `Label` made into a
          flex container gets a different box height from a plain one, so this
          field sat a few pixels off from the plain-labelled field beside it in
          the same grid row — visible as soon as two of them are side by side. */}
      <Label htmlFor={id}>
        <span className="inline-flex items-center gap-1.5">
          {label}
          {stale ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <AlertTriangle className="size-3.5 text-status-warn" aria-hidden />
              </TooltipTrigger>
              <TooltipContent>{t("workflow.templates.staleHint")}</TooltipContent>
            </Tooltip>
          ) : null}
        </span>
      </Label>
      <Select value={value ?? NONE} onValueChange={(next) => onChange(next === NONE ? null : next)}>
        <SelectTrigger id={id} {...fieldErrorProps(refusal, path)}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>{noneLabel}</SelectItem>
          {stale ? (
            <SelectItem value={value}>{t("workflow.templates.stale", { name: value })}</SelectItem>
          ) : null}
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <TemplateFieldError refusal={refusal} path={path} />
    </div>
  );
}
