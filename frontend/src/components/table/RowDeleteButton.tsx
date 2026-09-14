// frontend/src/components/table/RowDeleteButton.tsx
//
// The delete action of a table row, written once. Six tables had their own copy
// of the same button and one of them (knowledge) had drifted into a bare icon
// with no label, which reads as a different affordance from the icon+text
// delete every other table shows.
//
// It never owns the confirmation dialog. A dialog rendered inside a clickable
// row closes THROUGH the row and triggers its navigation, so the tables hoist
// the dialog to table level and this button only reports the intent — the same
// split SkillRowActions already used.
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

interface Props {
  /** Spoken label, normally "<Delete>: <row name>" — the visible text is the
   *  same for every row, so the name has to be in here. */
  ariaLabel: string;
  disabled?: boolean;
  onDelete: () => void;
}

export function RowDeleteButton({ ariaLabel, disabled = false, onDelete }: Props) {
  const { t } = useTranslation();
  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      className="text-muted-foreground hover:text-destructive"
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={(e) => {
        // The row is clickable; deleting must not also navigate into the thing
        // being deleted.
        e.stopPropagation();
        onDelete();
      }}
    >
      <Trash2 className="mr-1.5 size-3.5" />
      {t("common.delete")}
    </Button>
  );
}
