// components/settings/ModelForm.tsx
// react-hook-form + zod form for creating / editing a model config.
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import type { Model, ModelCreate, ModelPatch, ModelProvider } from "@/lib/api/models";
import { modelSchema } from "./modelSchema";
import type { ModelFormValues } from "./modelSchema";

const PROVIDERS: ModelProvider[] = ["anthropic", "openai", "ollama"];

interface Props {
  existing?: Model;
  onSubmit: (values: ModelCreate | ModelPatch) => Promise<void>;
  onCancel: () => void;
  submitError?: Error | null;
}

export function ModelForm({ existing, onSubmit, onCancel, submitError }: Props) {
  const { t } = useTranslation();
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<ModelFormValues>({
    resolver: zodResolver(modelSchema),
    defaultValues: {
      display_name: existing?.display_name ?? "",
      provider: existing?.provider ?? "anthropic",
      model: existing?.model ?? "",
      credential_ref: existing?.credential_ref ?? "",
      base_url: existing?.base_url ?? "",
      is_default: existing?.is_default ?? false,
    },
  });

  const provider = watch("provider");
  const isDefault = watch("is_default");
  const needsCredential = provider !== "ollama";
  const needsBaseUrl = provider === "ollama" || provider === "openai";

  const handleFormSubmit = async (values: ModelFormValues) => {
    const payload = {
      ...values,
      credential_ref: values.credential_ref?.trim() || null,
      base_url: values.base_url?.trim() || null,
    };
    await onSubmit(payload);
  };

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
      <div className="grid gap-1.5">
        <Label htmlFor="display_name">{t("settings.models.displayName")}</Label>
        <Input
          id="display_name"
          {...register("display_name")}
          placeholder={t("settings.models.displayNamePlaceholder")}
        />
        {errors.display_name && (
          <p className="text-xs text-destructive">{errors.display_name.message}</p>
        )}
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="provider">{t("settings.models.provider")}</Label>
        <Select
          value={provider}
          onValueChange={(v) => setValue("provider", v as ModelProvider)}
        >
          <SelectTrigger id="provider" aria-label={t("settings.models.provider")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROVIDERS.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="model">{t("settings.models.modelId")}</Label>
        <Input
          id="model"
          {...register("model")}
          placeholder={t("settings.models.modelIdPlaceholder")}
        />
        {errors.model && (
          <p className="text-xs text-destructive">{errors.model.message}</p>
        )}
      </div>

      {needsCredential && (
        <div className="grid gap-1.5">
          <Label htmlFor="credential_ref">{t("settings.models.credentialRef")}</Label>
          <Input
            id="credential_ref"
            {...register("credential_ref")}
            placeholder={t("settings.models.credentialRefPlaceholder")}
          />
        </div>
      )}

      {needsBaseUrl && (
        <div className="grid gap-1.5">
          <Label htmlFor="base_url">{t("settings.models.baseUrl")}</Label>
          <Input
            id="base_url"
            {...register("base_url")}
            placeholder={t("settings.models.baseUrlPlaceholder")}
          />
          {errors.base_url && (
            <p className="text-xs text-destructive">{errors.base_url.message}</p>
          )}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Switch
          id="is_default"
          checked={!!isDefault}
          onCheckedChange={(v) => setValue("is_default", v)}
        />
        <Label htmlFor="is_default">{t("settings.models.setDefault")}</Label>
      </div>

      {submitError && (
        <p className="text-sm text-destructive">
          {translateApiError(t, submitError)}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? t("common.saving") : t("common.save")}
        </Button>
      </div>
    </form>
  );
}
