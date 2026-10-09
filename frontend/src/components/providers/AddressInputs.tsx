// src/components/providers/AddressInputs.tsx — the OpenAI- and Anthropic-compatible address fields of Add and Edit.
//
// Each field says which agent uses it; a form shows only the fields its vendor
// has (both for Custom and for a saved remote connection). At least one is
// required, checked by the form's schema (ADR one-connection-serves-both-wires).
import type { UseFormRegisterReturn } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AddressFields } from "@/lib/providers/addresses";
import { FieldError } from "./FieldError";

interface Props {
  /** Prefix of the inputs' ids. */
  idPrefix: string;
  show: AddressFields;
  openai: UseFormRegisterReturn;
  anthropic: UseFormRegisterReturn;
  errors: { openai?: string; anthropic?: string };
  /** Show the "fill what the gateway serves" hint (Custom, Edit). */
  hint?: boolean;
}

export function AddressInputs({ idPrefix, show, openai, anthropic, errors, hint }: Props) {
  const { t } = useTranslation();
  const both = show.openai && show.anthropic;
  const rows = [
    { key: "openai" as const, field: openai },
    { key: "anthropic" as const, field: anthropic },
  ].filter((r) => show[r.key]);
  return (
    <div className="flex flex-col gap-4">
      {rows.map(({ key, field }) => {
        const id = `${idPrefix}-${key}`;
        return (
          <div key={key} className="flex flex-col gap-1.5">
            <Label htmlFor={id} required={!both}>
              {t(`providers.address.${key}.label`)}
            </Label>
            <Input
              id={id}
              inputMode="url"
              className="font-mono text-xs"
              aria-describedby={`${id}-error ${id}-help`}
              {...field}
            />
            <FieldError id={`${id}-error`} message={errors[key]} />
            <p id={`${id}-help`} className="text-xs text-text-muted">
              {t(`providers.address.${key}.help`)}
            </p>
          </div>
        );
      })}
      {both && hint ? (
        <p className="-mt-2 text-xs text-text-muted">{t("providers.address.bothHint")}</p>
      ) : null}
    </div>
  );
}
