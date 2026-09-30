// src/components/providers/ModalitySelect.tsx — the five-value picker for what KIND of model a curated entry is.
//
// Text, embedding, image, video or audio (spec provider-switching "Store a
// modality with each curated model"). Introspection guesses it from the id;
// this is where the user corrects the guess.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MODALITIES, type Modality } from "@/lib/api/providers";

interface Props {
  value: Modality;
  onChange: (value: Modality) => void;
  disabled?: boolean;
  /** Appended to the trigger's accessible name so one list can hold many. */
  label: string;
}

export function ModalitySelect({ value, onChange, disabled, label }: Props) {
  const { t } = useTranslation();
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Modality)} disabled={disabled}>
      <SelectTrigger
        className="h-7 w-32 text-xs"
        aria-label={t("providers.models.typeOf", { id: label })}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {MODALITIES.map((m) => (
          <SelectItem key={m} value={m}>
            {t(`providers.modalities.${m}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
