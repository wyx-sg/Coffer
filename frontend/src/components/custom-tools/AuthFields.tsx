// src/components/custom-tools/AuthFields.tsx — a group's auth header (name + prefix, one compound field) and its secret.
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Input } from "@/components/ui/input";
import type { AuthDraft } from "@/lib/customTools/drafts";
import { FormField } from "./FormField";
import { SecretPicker } from "./SecretPicker";

interface Props {
  value: AuthDraft;
  onChange: (value: AuthDraft) => void;
  /** The line under the header field, e.g. "From the spec's security scheme." */
  headerHelp?: ReactNode;
  disabled?: boolean;
}

export function AuthFields({ value, onChange, headerHelp, disabled }: Props) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <>
      <FormField
        label={t("customTools.fields.authHeader")}
        htmlFor={`${id}-header`}
        help={headerHelp}
      >
        {/* One value made of parts: the header's name and the prefix before the secret. */}
        <div className="flex gap-2">
          <Input
            id={`${id}-header`}
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
            {t("customTools.fields.secretHelpAfter")}
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
