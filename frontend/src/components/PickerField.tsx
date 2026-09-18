// frontend/src/components/PickerField.tsx
// The one shape for "something you pick, never type": a read-only display of
// what is chosen, a Browse button, and an optional Clear.
//
// It exists because the two pickers had drifted apart. A folder was picked
// through a styled field with a translated button; a file was a bare
// `<input type="file">`, which renders the BROWSER's own control — "Choose
// file / No file chosen", in English, whatever the app's language, with its
// own metrics. Two controls doing the same job in the same dialog should not
// look like they came from different programs, so the display and the row
// live here and each picker supplies only its own button.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

interface Props {
  /** What is currently chosen, as text: a path, or a filename. */
  value: string | null;
  /** Shown when nothing is chosen yet. */
  placeholder?: string;
  ariaLabel?: string;
  inputId?: string;
  /** The picker's own trigger — a Browse button, or whatever opens it. */
  action: React.ReactNode;
  /** When given, a Clear button appears once something is chosen. */
  onClear?: () => void;
}

export function PickerField({ value, placeholder, ariaLabel, inputId, action, onClear }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      <input
        id={inputId}
        aria-label={ariaLabel}
        className="block w-full rounded-md border bg-muted px-2 py-1 font-mono text-xs"
        placeholder={placeholder}
        value={value ?? ""}
        readOnly
      />
      {action}
      {onClear && value ? (
        <Button type="button" variant="ghost" size="sm" onClick={onClear}>
          {t("common.clear")}
        </Button>
      ) : null}
    </div>
  );
}
