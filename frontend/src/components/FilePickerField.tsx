// frontend/src/components/FilePickerField.tsx
// Choose a file from this machine, in the same shape as choosing a folder.
//
// The browser's own `<input type="file">` is the only way to get at bytes, so
// it is still what does the work — but it is hidden, and the affordance is the
// same read-only field and Browse button the folder picker has. A raw file
// input renders the browser's control, whose label is in the browser's
// language rather than the app's.
//
// It shows the NAME and not a path on purpose: a browser hands the page a
// `File`, never where it came from. The daemon stores the bytes under the
// run's own directory, so the path it will have is the
// run's to decide and not this field's to claim.
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import { PickerField } from "@/components/PickerField";
import { Button } from "@/components/ui/button";

interface Props {
  value: File | null;
  onChange: (file: File | null) => void;
  placeholder?: string;
  ariaLabel?: string;
  inputId?: string;
  disabled?: boolean;
}

export function FilePickerField({
  value,
  onChange,
  placeholder,
  ariaLabel,
  inputId,
  disabled = false,
}: Props) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);

  return (
    <PickerField
      inputId={inputId}
      ariaLabel={ariaLabel}
      value={value?.name ?? null}
      placeholder={placeholder}
      onClear={() => onChange(null)}
      action={
        <>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => input.current?.click()}
          >
            {t("picker.browse")}
          </Button>
          {/* Hidden on purpose: the Button above is the affordance. */}
          <input
            ref={input}
            type="file"
            className="hidden"
            aria-hidden
            tabIndex={-1}
            onChange={(e) => {
              const picked = e.target.files?.[0] ?? null;
              // Reset first, so re-picking the SAME file fires change again.
              e.target.value = "";
              if (picked) onChange(picked);
            }}
          />
        </>
      }
    />
  );
}
