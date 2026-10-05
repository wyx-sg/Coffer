// src/components/secret/AuthSchemeSelect.tsx — the scheme Coffer puts in front of a header's secret
// when it sends (`Authorization: Bearer <key>`): Bearer, Token or None (the secret goes as is).
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AUTH_SCHEMES, type AuthScheme } from "@/lib/authScheme";

const NONE = "none";

interface Props {
  /** The header's name, for the accessible name. */
  rowKey: string;
  value: AuthScheme | null;
  onChange: (scheme: AuthScheme | null) => void;
}

export function AuthSchemeSelect({ rowKey, value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <Select
      value={value ?? NONE}
      onValueChange={(v) => onChange(v === NONE ? null : (v as AuthScheme))}
    >
      <SelectTrigger
        className="w-[92px] shrink-0 text-xs"
        aria-label={t("secretRows.schemeOf", { key: rowKey })}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {AUTH_SCHEMES.map((s) => (
          <SelectItem key={s} value={s}>
            {s}
          </SelectItem>
        ))}
        <SelectItem value={NONE}>{t("secretRows.schemeNone")}</SelectItem>
      </SelectContent>
    </Select>
  );
}
