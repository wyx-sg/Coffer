// components/settings/ModalitySelect.tsx — the five-value picker that says what
// KIND of model a curated entry is (provider-switching FR-029): text, embedding,
// image, video or audio. One endpoint serves several kinds from one key, and a
// downstream picker asks for the kind it needs, so the answer has to be sayable
// per model — introspection guesses it from the id, this is where the user
// corrects the guess.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MODALITIES, type Modality } from "@/lib/api/providers";

export function ModalitySelect({
  value,
  onChange,
  disabled,
  /** Appended to the trigger's accessible name so one table can hold many. */
  label,
}: {
  value: Modality;
  onChange: (value: Modality) => void;
  disabled?: boolean;
  label: string;
}) {
  const { t } = useTranslation();
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Modality)} disabled={disabled}>
      <SelectTrigger
        className="h-8 w-36 text-xs"
        aria-label={`${t("settings.connections.detail.modality")}: ${label}`}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {MODALITIES.map((m) => (
          <SelectItem key={m} value={m}>
            {t(`settings.connections.detail.modalities.${m}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
