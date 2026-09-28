// frontend/src/components/table/RowDeleteButton.tsx
//
// The delete action of a table row, written once, in the shared table-action
// look (TableActionButton).
//
// It never owns the confirmation dialog. A dialog rendered inside a clickable
// row closes THROUGH the row and triggers its navigation, so the tables hoist
// the dialog to table level and this button only reports the intent — the same
// split SkillRowActions already used.
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { TableActionButton } from "@/components/table/TableActionButton";

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
    <TableActionButton
      icon={Trash2}
      label={t("common.delete")}
      destructive
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onDelete}
    />
  );
}
