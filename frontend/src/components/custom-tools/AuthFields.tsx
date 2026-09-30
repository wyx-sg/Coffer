// src/components/custom-tools/AuthFields.tsx — a group's auth header (one select of the usual headers, or
// a custom name + prefix) and the secret its value comes from.
import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AUTH_PRESETS,
  authLine,
  presetOf,
  type AuthDraft,
  type AuthPreset,
} from "@/lib/customTools/drafts";
import { FormField } from "./FormField";
import { SecretPicker } from "./SecretPicker";

interface Props {
  value: AuthDraft;
  onChange: (value: AuthDraft) => void;
  /** The line under the header field, e.g. "From the spec's security scheme." */
  headerHelp?: ReactNode;
  /** Name the choices by scheme ("Bearer token (HTTP)"), as an import reads them. */
  schemes?: boolean;
  disabled?: boolean;
}

export function AuthFields({ value, onChange, headerHelp, schemes = false, disabled }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const [custom, setCustom] = useState(() => presetOf(value) === "custom");
  const preset: AuthPreset = custom ? "custom" : presetOf(value);
  const pick = (key: AuthPreset) => {
    if (key === "custom") return setCustom(true);
    setCustom(false);
    const found = AUTH_PRESETS.find((p) => p.key === key);
    if (found) onChange({ ...value, header: found.header, prefix: found.prefix });
  };
  const optionLabel = (key: AuthPreset, header: string, prefix: string) =>
    schemes ? t(`customTools.auth.scheme.${key}`) : authLine(header, prefix);

  return (
    <>
      <FormField
        label={schemes ? t("customTools.definition.auth") : t("customTools.fields.authHeader")}
        htmlFor={`${id}-header`}
        help={headerHelp}
      >
        <Select
          value={preset}
          onValueChange={(next) => pick(next as AuthPreset)}
          disabled={disabled}
        >
          <SelectTrigger id={`${id}-header`} className={schemes ? undefined : "font-mono"}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AUTH_PRESETS.map((p) => (
              <SelectItem key={p.key} value={p.key} className={schemes ? undefined : "font-mono"}>
                {optionLabel(p.key, p.header, p.prefix)}
              </SelectItem>
            ))}
            <SelectItem value="custom">{t("customTools.auth.custom")}</SelectItem>
          </SelectContent>
        </Select>
        {preset === "custom" ? (
          // One value made of parts: the header's name and the prefix before the secret.
          <div className="flex gap-2">
            <Input
              className="flex-1 font-mono"
              value={value.header}
              disabled={disabled}
              aria-label={t("customTools.fields.headerName")}
              onChange={(e) => onChange({ ...value, header: e.target.value })}
            />
            <Input
              className="w-32 font-mono"
              value={value.prefix}
              disabled={disabled}
              placeholder={t("customTools.fields.prefixPlaceholder")}
              aria-label={t("customTools.fields.headerPrefix")}
              onChange={(e) => onChange({ ...value, prefix: e.target.value })}
            />
          </div>
        ) : null}
      </FormField>
      <FormField
        label={t("customTools.fields.secret")}
        htmlFor={`${id}-secret`}
        help={
          <>
            {t("customTools.fields.secretHelpBefore")}
            <Link to="/secrets" className="text-accent-text hover:underline">
              {t("customTools.fields.secretHelpLink")}
            </Link>
            {schemes
              ? t("customTools.fields.secretHelpAfterAgents")
              : t("customTools.fields.secretHelpAfter")}
          </>
        }
      >
        <SecretPicker
          id={`${id}-secret`}
          value={value.secret}
          disabled={disabled}
          onChange={(secret) => onChange({ ...value, secret })}
        />
      </FormField>
    </>
  );
}
