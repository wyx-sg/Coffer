// components/settings/ProviderForm.tsx — create a provider profile (spec 011).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { translateApiError } from "@/lib/api/errors";
import type { ProviderCreate, WireFormat } from "@/lib/api/providers";

interface Props {
  submitError?: unknown;
  pending: boolean;
  onSubmit: (values: ProviderCreate) => Promise<void> | void;
  onCancel: () => void;
}

export function ProviderForm({ submitError, pending, onSubmit, onCancel }: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [wireFormat, setWireFormat] = useState<WireFormat>("anthropic");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [secret, setSecret] = useState("");

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit({
          name,
          wire_format: wireFormat,
          base_url: baseUrl,
          model,
          secret_value: secret,
        });
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="p-name">{t("settings.providers.name")}</Label>
        <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-wire">{t("settings.providers.wireFormat")}</Label>
        <select
          id="p-wire"
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
          value={wireFormat}
          onChange={(e) => setWireFormat(e.target.value as WireFormat)}
        >
          <option value="anthropic">anthropic</option>
          <option value="openai">openai</option>
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-base">{t("settings.providers.baseUrl")}</Label>
        <Input id="p-base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-model">{t("settings.providers.model")}</Label>
        <Input id="p-model" value={model} onChange={(e) => setModel(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-secret">{t("settings.providers.secret")}</Label>
        <PasswordInput
          id="p-secret"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          required
        />
      </div>
      {submitError != null && (
        <p className="text-sm text-destructive">{translateApiError(t, submitError)}</p>
      )}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={pending}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
