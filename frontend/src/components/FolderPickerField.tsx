// frontend/src/components/FolderPickerField.tsx — spec agent-registry "Offer a
// folder picker for a custom config directory"; spec daemon "Browse folders without
// reading files" and "Open the host's native folder picker".
// A folder is picked, never typed: the native dialog on desktop, the daemon's
// native dialog then an in-app browser on web. The row it sits in — read-only
// display, Browse, optional Clear — is `PickerField`, shared with the file
// picker so the two do not look like they came from different programs.
import { FolderPicker } from "@/components/FolderPicker";
import { PickerField } from "@/components/PickerField";

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
  return (
    <PickerField
      inputId={inputId}
      ariaLabel={ariaLabel}
      value={value}
      placeholder={placeholder}
      onClear={clearable ? () => onChange(null) : undefined}
      action={<FolderPicker value={value} onChange={(p) => onChange(p)} />}
    />
  );
}
