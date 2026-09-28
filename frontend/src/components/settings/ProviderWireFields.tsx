// components/settings/ProviderWireFields.tsx — the two pickers ProviderForm
// uses to choose a connection's wire: the protocol itself (edit mode, and
// "Custom" on create) and the provider preset that fills protocol + endpoint.
import { Controller, type Control } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Protocol } from "@/lib/api/providers";
import { PRESETS, PROTOCOL_LABEL_KEY, SELECTABLE_PROTOCOLS } from "./connectionPresets";
import type { ProviderFormValues } from "./providerFormSchema";

/** Required fields carry a mark after the label; the label text itself stays
 *  clean so its accessible name is just the word. */
export const REQUIRED = "after:ml-0.5 after:text-destructive after:content-['*']";

export function ProtocolPicker({
  id,
  control,
}: {
  id: string;
  control: Control<ProviderFormValues>;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className={REQUIRED}>
        {t("settings.connections.wireFormat")}
      </Label>
      <Controller
        control={control}
        name="protocol"
        render={({ field }) => (
          <Select value={field.value} onValueChange={(v) => field.onChange(v as Protocol)}>
            <SelectTrigger id={id}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SELECTABLE_PROTOCOLS.map((p) => (
                <SelectItem key={p} value={p}>
                  {t(PROTOCOL_LABEL_KEY[p])}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />
    </div>
  );
}

export function PresetPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      <Label htmlFor="p-preset">{t("settings.connections.provider")}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id="p-preset">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PRESETS.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.id === "custom" ? t("settings.connections.customProvider") : p.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
