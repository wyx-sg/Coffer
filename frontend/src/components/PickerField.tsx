// frontend/src/components/PickerField.tsx
// The one shape for "something you pick, never type": a read-only display of
// what is chosen, a Browse button, and an optional Clear. A caller that also
// accepts a typed or pasted value (the skill import path) passes `onType`, and
// the display becomes an ordinary text input beside the same Browse button.
//
// It exists because the two pickers had drifted apart. A folder was picked
// through a styled field with a translated button; a file was a bare
// `<input type="file">`, which renders the BROWSER's own control — "Choose
// file / No file chosen", in English, whatever the app's language, with its
// own metrics. Two controls doing the same job in the same dialog should not
// look like they came from different programs, so the display and the row
// live here and each picker supplies only its own button.
//
// Foundations-Pickers "Folder picker": the field is the 30px text field with
// the value in mono 12 (the read-only look while it only displays), and the
// picker's button sits outside it at the same height. `invalid` is the
// "folder missing" state: a danger border, the old path left visible, and the
// caller's message under the row.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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
  /** When given, the display is editable and reports each typed or pasted value. */
  onType?: (value: string) => void;
  /** The chosen value no longer resolves (e.g. the folder was moved). */
  invalid?: boolean;
}

export function PickerField({
  value,
  placeholder,
  ariaLabel,
  inputId,
  action,
  onClear,
  onType,
  invalid = false,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      <Input
        id={inputId}
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        className="min-w-0 truncate font-mono text-xs"
        placeholder={placeholder}
        value={value ?? ""}
        readOnly={!onType}
        onChange={onType ? (e) => onType(e.target.value) : undefined}
        spellCheck={onType ? false : undefined}
        autoComplete={onType ? "off" : undefined}
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
