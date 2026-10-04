// src/components/providers/ModalitySelect.tsx — a model's type, as quiet text with a menu behind it.
//
// Text, embedding, image, video or audio (spec provider-switching "Store a
// modality with each curated model"). Introspection guesses it from the id;
// this is where the user corrects the guess. The control is ghost — no border,
// gray text and a chevron, right-aligned, a hover background — so a list of
// models does not read as a column of form fields.
import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { MODALITIES, type Modality } from "@/lib/api/providers";
import { cn } from "@/lib/utils";

interface Props {
  value: Modality;
  onChange: (value: Modality) => void;
  disabled?: boolean;
  /** Appended to the trigger's accessible name so one list can hold many. */
  label: string;
}

export function ModalitySelect({ value, onChange, disabled, label }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-label={t("providers.models.typeOf", { id: label })}
          className={cn(
            "inline-flex h-7 w-full items-center justify-end gap-1 rounded-md px-2 text-xs text-text-muted outline-none",
            "hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-focus-ring disabled:opacity-disabled",
            open && "bg-surface-hover",
          )}
        >
          {t(`providers.modalities.${value}`)}
          <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-44 p-1" align="end">
        <div role="listbox" aria-label={t("providers.models.typeOf", { id: label })}>
          {MODALITIES.map((m) => (
            <button
              key={m}
              type="button"
              role="option"
              aria-selected={m === value}
              onClick={() => {
                setOpen(false);
                if (m !== value) onChange(m);
              }}
              className={cn(
                "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text",
                "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                m === value && "bg-surface-selected font-label",
              )}
            >
              <span className="min-w-0 flex-1 truncate">{t(`providers.modalities.${m}`)}</span>
              {m === value ? <Check className="size-3.5 text-accent-text" aria-hidden /> : null}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
