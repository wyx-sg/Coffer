// frontend/src/components/agents/FolderPickerField.tsx — spec 004 FR-023/FR-024/FR-042, ADR-036.
// A read-only path display paired with the FolderPicker button: the folder is
// picked (native dialog on desktop, daemon native dialog → in-app browser on
// web), never typed. Replaces the raw text inputs that used to sit beside the
// picker. `clearable` adds a reset button for optional fields.
import { useTranslation } from "react-i18next";

import { FolderPicker } from "@/components/agents/FolderPicker";
import { Button } from "@/components/ui/button";

export function FolderPickerField({
  value,
  onChange,
  placeholder,
  ariaLabel,
  inputId,
  clearable = false,
}: {
  value: string | null;
  onChange: (path: string | null) => void;
  placeholder?: string;
  ariaLabel?: string;
  inputId?: string;
  clearable?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      <input
        id={inputId}
        aria-label={ariaLabel}
        className="block w-full rounded border bg-muted px-2 py-1 font-mono text-xs"
        placeholder={placeholder}
        value={value ?? ""}
        readOnly
      />
      <FolderPicker value={value} onChange={(p) => onChange(p)} />
      {clearable && value ? (
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange(null)}>
          {t("common.clear")}
        </Button>
      ) : null}
    </div>
  );
}
