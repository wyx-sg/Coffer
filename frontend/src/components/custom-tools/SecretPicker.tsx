// src/components/custom-tools/SecretPicker.tsx — pick a stored secret by its Secrets-page name, or none.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSecretNames } from "@/lib/hooks/useSecretNames";

/** Radix Select has no empty value; "no secret" is this sentinel. */
const NONE = "__none__";

interface Props {
  id?: string;
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
}

export function SecretPicker({ id, value, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const { names } = useSecretNames();
  // A bound secret that is not stored (missing) still shows as the choice.
  const options = value && !names.includes(value) ? [value, ...names] : names;
  return (
    <Select
      value={value ?? NONE}
      onValueChange={(next) => onChange(next === NONE ? null : next)}
      disabled={disabled}
    >
      <SelectTrigger id={id} className="font-mono">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{t("customTools.fields.noSecret")}</SelectItem>
        {options.map((name) => (
          <SelectItem key={name} value={name} className="font-mono">
            {name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
