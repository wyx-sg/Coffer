// frontend/src/components/workflow/TemplatePositionField.tsx
// Where a stage runs in the workflow, or a task runs in its stage.
//
// The order IS the forward path (FR-005), so this is an edit to the flow and
// not a layout preference — which is why it is a field of the thing being
// edited, in that thing's dialog, beside everything else about it. It used to
// be a pair of arrows stuck to the box on the map; the map is a map now, and
// a map does not carry controls.
//
// A select rather than a drag handle: a keyboard reaches it, it says what the
// positions ARE, and it needs no drag-and-drop dependency to move something
// from sixth to first in one act.
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Props {
  id: string;
  /** Zero-based, as the arrays are. */
  value: number;
  /** How many there are to sit among, counting this one. */
  count: number;
  onChange: (index: number) => void;
  /** What the positions are of — "Runs at" reads differently for each. */
  label: string;
  hint: string;
  disabled?: boolean;
}

export function TemplatePositionField({
  id,
  value,
  count,
  onChange,
  label,
  hint,
  disabled = false,
}: Props) {
  const { t } = useTranslation();
  // Nothing to choose between when it is the only one; showing a select with
  // a single option would be offering a decision that does not exist.
  if (count <= 1) return null;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={String(value)}
        disabled={disabled}
        onValueChange={(next) => onChange(Number(next))}
      >
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Array.from({ length: count }, (_, index) => (
            <SelectItem key={index} value={String(index)}>
              {t("workflow.templates.positionOption", { position: index + 1, count })}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
