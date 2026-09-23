// frontend/src/components/workflow/TemplateFieldError.tsx
// The refusal, rendered AT the field it names.
//
// The daemon's refusal already carries the JSON path of the offending field,
// so a banner over the whole form would be throwing away the one
// thing that makes it actionable. Every control in the editor pairs with one
// of these and points at it with `aria-describedby`, so the field is announced
// with its reason rather than merely marked invalid.
import { useTranslation } from "react-i18next";

import { errorId, messageFor, type TemplateRefusal } from "@/lib/workflow/templateErrors";

interface Props {
  refusal: TemplateRefusal | null;
  /** This field's JSON path, e.g. `stages[1].nodes[0].skill`. */
  path: string;
}

export function TemplateFieldError({ refusal, path }: Props) {
  const { t } = useTranslation();
  const message = messageFor(refusal, path);
  if (message === undefined) return null;
  return (
    <p id={errorId(path)} role="alert" className="text-xs text-destructive">
      {t("workflow.templates.refused", { reason: message })}
    </p>
  );
}
