// src/components/providers/AddEndpointStep.tsx — step 1 of Add: vendor, protocol, name, base URL, key, and Test.
//
// A vendor fills the protocol and base URL; Custom asks for the protocol by
// what can use it. The key is a new value, stored as a new secret when the
// provider is added — write-only, never shown again. The local path (Ollama /
// a runtime on this Mac) has no key: detection finds what answers instead.
import type { ReactNode } from "react";
import type { UseFormReturn } from "react-hook-form";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { CUSTOM_PROTOCOLS, PRESETS, type PresetId } from "@/lib/providers/presets";
import { FieldError } from "./FieldError";
import { ProtocolCards } from "./ProtocolCards";
import { VendorGrid } from "./VendorGrid";
import type { EndpointValues } from "./providerSchemas";

interface Props {
  form: UseFormReturn<EndpointValues>;
  presetId: PresetId;
  onPreset: (id: PresetId) => void;
  /** The local path's detection panel, in place of the key field. */
  localPanel: ReactNode;
  /** Local path: Name shows once a runtime is chosen (or an address typed). */
  showName: boolean;
  /** Local path: the address field shows only when detection found nothing. */
  showUrl: boolean;
  /** The Test verdict. */
  result: ReactNode;
  /** Any edit invalidates the last Test. */
  onEdited: () => void;
}

export function AddEndpointStep({
  form,
  presetId,
  onPreset,
  localPanel,
  showName,
  showUrl,
  result,
  onEdited,
}: Props) {
  const { t } = useTranslation();
  const { register, watch, setValue, formState } = form;
  const { errors } = formState;
  const local = watch("local");
  const protocol = watch("protocol");
  const vendors = PRESETS.map((p) => ({
    value: p.id,
    label: p.id === "custom" ? t("providers.add.custom") : p.label,
  }));
  const protocols = presetId === "custom" ? CUSTOM_PROTOCOLS : [];
  const edited = { onChange: onEdited };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-label text-text">{t("providers.add.vendor")}</span>
        <VendorGrid
          label={t("providers.add.vendor")}
          value={presetId}
          options={vendors}
          onChange={onPreset}
        />
        <p className="text-xs text-text-muted">
          {local ? t("providers.add.vendorHintLocal") : t("providers.add.vendorHint")}
        </p>
      </div>
      {!local && presetId === "custom" ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-label text-text">{t("providers.fields.protocol")}</span>
          <ProtocolCards
            value={protocol}
            options={protocols}
            onChange={(p) => {
              setValue("protocol", p);
              onEdited();
            }}
          />
        </div>
      ) : null}
      {local ? localPanel : null}
      {!local || showName ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pa-name" required>
            {t("providers.fields.name")}
          </Label>
          <Input id="pa-name" aria-describedby="pa-name-error" {...register("name")} />
          <FieldError id="pa-name-error" message={errors.name?.message} />
        </div>
      ) : null}
      {!local || showUrl ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pa-base" required={!local}>
            {t("providers.fields.baseUrl")}
          </Label>
          <Input
            id="pa-base"
            inputMode="url"
            className="font-mono text-xs"
            placeholder={local ? t("providers.add.localUrlPlaceholder") : undefined}
            aria-describedby="pa-base-error"
            {...register("baseUrl", edited)}
          />
          <FieldError id="pa-base-error" message={errors.baseUrl?.message} />
          {local ? (
            <p className="text-xs text-text-muted">{t("providers.add.local.urlHint")}</p>
          ) : null}
        </div>
      ) : null}
      {local ? null : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pa-secret" required>
            {t("providers.fields.apiKey")}
          </Label>
          <PasswordInput
            id="pa-secret"
            autoComplete="off"
            className="font-mono text-xs"
            aria-describedby="pa-secret-error"
            {...register("secret", edited)}
          />
          <FieldError id="pa-secret-error" message={errors.secret?.message} />
          <p className="text-xs text-text-muted">
            {t("providers.add.keyHint")}{" "}
            <Link
              to="/secrets"
              className="font-label text-accent-text no-underline hover:underline"
            >
              {t("providers.key.manage")}
            </Link>
          </p>
        </div>
      )}
      {result}
    </div>
  );
}
