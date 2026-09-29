// src/components/resource/ResourceTitleField.tsx
// The title input every kind's edit form carries: free text up to 80
// characters, shown in place of the name; an empty field clears it.
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TITLE_MAX_LENGTH } from "@/lib/resourceTitle";

interface Props {
  id: string;
  value: string;
  onChange: (value: string) => void;
  /** The resource's name, shown as the placeholder: what surfaces fall back to. */
  name: string;
  disabled?: boolean;
}

export function ResourceTitleField({ id, value, onChange, name, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{t("resources.titleField.label")}</Label>
      <Input
        id={id}
        value={value}
        maxLength={TITLE_MAX_LENGTH}
        placeholder={name}
        disabled={disabled}
        aria-describedby={`${id}-hint`}
        onChange={(e) => onChange(e.target.value)}
      />
      <p id={`${id}-hint`} className="text-xs text-muted-foreground">
        {t("resources.titleField.hint")}
      </p>
    </div>
  );
}
