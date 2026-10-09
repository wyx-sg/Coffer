// src/components/providers/AddEndpointStep.tsx — step 1 of Add: vendor, name, addresses, key, and Test.
//
// A vendor fills its addresses: the OpenAI-compatible one Codex uses and the
// Anthropic-compatible one Claude Code uses, whichever the vendor has (both for
// DeepSeek), for the region picked when the vendor has two. Custom shows both, and the person fills what their gateway
// serves; no protocol is asked for (ADR one-connection-serves-both-wires). The
// key is the one secret field: a stored secret, or a pasted value stored as a
// new secret when the provider is added. The local path (Ollama / a runtime on
// this Mac) has no key: detection finds what answers instead.
import { useEffect, useState, type ReactNode } from "react";
import { Controller, type UseFormReturn } from "react-hook-form";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SecretField } from "@/components/secret/SecretField";
import { presetAddresses, presetFields, type Region } from "@/lib/providers/addresses";
import { PRESETS, presetById, type PresetId } from "@/lib/providers/presets";
import { AddressInputs } from "./AddressInputs";
import { FieldError } from "./FieldError";
import { RegionChoice } from "./RegionChoice";
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
  const vendors = PRESETS.map((p) => ({
    value: p.id,
    label: p.id === "custom" ? t("providers.add.custom") : p.label,
  }));
  const preset = presetById(presetId);
  // A vendor whose addresses and keys differ by region asks which one.
  const [region, setRegion] = useState<Region>("intl");
  useEffect(() => setRegion("intl"), [presetId]);
  const pickRegion = (next: Region) => {
    setRegion(next);
    const at = presetAddresses(preset, next);
    setValue("openaiUrl", at.openai);
    setValue("anthropicUrl", at.anthropic);
    onEdited();
  };
  const vendorLabel = vendors.find((v) => v.value === presetId)?.label ?? "";
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
      {!local && preset.cn ? <RegionChoice value={region} onChange={pickRegion} /> : null}
      {!local ? (
        <AddressInputs
          idPrefix="pa"
          show={presetFields(preset)}
          openai={register("openaiUrl", edited)}
          anthropic={register("anthropicUrl", edited)}
          errors={{ openai: errors.openaiUrl?.message, anthropic: errors.anthropicUrl?.message }}
          hint={presetId === "custom"}
        />
      ) : null}
      {local && showUrl ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pa-base">{t("providers.fields.baseUrl")}</Label>
          <Input
            id="pa-base"
            inputMode="url"
            className="font-mono text-xs"
            placeholder={t("providers.add.localUrlPlaceholder")}
            aria-describedby="pa-base-error"
            {...register("baseUrl", edited)}
          />
          <FieldError id="pa-base-error" message={errors.baseUrl?.message} />
          <p className="text-xs text-text-muted">{t("providers.add.local.urlHint")}</p>
        </div>
      ) : null}
      {local ? null : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pa-secret" required>
            {t("providers.fields.apiKey")}
          </Label>
          <Controller
            control={form.control}
            name="secret"
            render={({ field }) => (
              <SecretField
                id="pa-secret"
                value={field.value}
                onChange={(next) => {
                  field.onChange(next);
                  onEdited();
                }}
                defaultName={t("providers.add.keyName", {
                  name: watch("name").trim() || vendorLabel,
                })}
                aria-label={t("providers.fields.apiKey")}
                invalid={errors.secret ? true : undefined}
                help={false}
              />
            )}
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
