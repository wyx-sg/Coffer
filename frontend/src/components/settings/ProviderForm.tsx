// components/settings/ProviderForm.tsx — add / edit an LLM connection (spec 011).
// A connection = key + endpoint + wire + model. Ollama is internal-only and has
// no key, so the credential field is hidden (and omitted from the body) when
// wire_format = ollama. In edit mode (`initial` set) the name + wire are fixed
// (they identify the resource / its projection target) and the secret is
// optional — left blank, the stored key is kept.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { ProviderModelField } from "@/components/settings/ProviderModelField";
import { translateApiError } from "@/lib/api/errors";
import {
  wireNeedsCredential,
  type Provider,
  type ProviderCreate,
  type ProviderPatch,
  type WireFormat,
} from "@/lib/api/providers";

interface Props {
  /** Present → edit an existing connection (name + wire locked, secret optional). */
  initial?: Provider;
  submitError?: unknown;
  pending: boolean;
  onSubmit: (values: ProviderCreate) => Promise<void> | void;
  /** Required when `initial` is set; receives the PATCH body. */
  onUpdate?: (patch: ProviderPatch) => Promise<void> | void;
  onCancel: () => void;
}

export function ProviderForm({ initial, submitError, pending, onSubmit, onUpdate, onCancel }: Props) {
  const { t } = useTranslation();
  const isEdit = initial != null;
  const [name, setName] = useState(initial?.name ?? "");
  const [wireFormat, setWireFormat] = useState<WireFormat>(initial?.wire_format ?? "anthropic");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [model, setModel] = useState(initial?.model ?? "");
  const [fastModel, setFastModel] = useState(initial?.fast_model ?? "");
  const [secret, setSecret] = useState("");

  const needsCredential = wireNeedsCredential(wireFormat);
  // Probe key: a freshly typed secret wins; otherwise reuse the stored ref so
  // test/fetch works in edit mode without re-entering the key.
  const probeCredentialRef = isEdit && !secret ? (initial?.credential_ref ?? null) : null;

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (isEdit) {
          // Name + wire are immutable; PATCH only the editable fields.
          const patch: ProviderPatch = { base_url: baseUrl, model };
          patch.fast_model = fastModel.trim() ? fastModel.trim() : null;
          if (needsCredential && secret) patch.secret_value = secret;
          await onUpdate?.(patch);
          return;
        }
        const values: ProviderCreate = {
          name,
          wire_format: wireFormat,
          base_url: baseUrl,
          model,
        };
        if (fastModel.trim()) values.fast_model = fastModel.trim();
        // Ollama has no key — send NEITHER secret_value nor credential_ref.
        if (needsCredential && secret) values.secret_value = secret;
        await onSubmit(values);
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="p-name">{t("settings.connections.name")}</Label>
        <Input
          id="p-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          disabled={isEdit}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-wire">{t("settings.connections.wireFormat")}</Label>
        <select
          id="p-wire"
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm disabled:opacity-50"
          value={wireFormat}
          onChange={(e) => setWireFormat(e.target.value as WireFormat)}
          disabled={isEdit}
        >
          <option value="anthropic">anthropic</option>
          <option value="openai">openai</option>
          <option value="ollama">ollama</option>
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-base">{t("settings.connections.baseUrl")}</Label>
        <Input id="p-base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required />
      </div>
      {needsCredential && (
        <div className="space-y-1.5">
          <Label htmlFor="p-secret">{t("settings.connections.secret")}</Label>
          <PasswordInput
            id="p-secret"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            required={!isEdit}
            placeholder={isEdit ? t("settings.connections.secretKeepBlank") : undefined}
          />
        </div>
      )}
      {/* Model field carries «测试连接»/«拉取模型», driven by the inline (not-yet
          -saved) secret above so the user can probe before saving (ADR-032 D6). */}
      <ProviderModelField
        provider={wireFormat}
        baseUrl={baseUrl || null}
        credentialRef={probeCredentialRef}
        secretValue={secret}
        model={model}
        onModelChange={setModel}
        kind="chat"
      />
      <div className="space-y-1.5">
        <Label htmlFor="p-fast">{t("settings.connections.fastModel")}</Label>
        <Input id="p-fast" value={fastModel} onChange={(e) => setFastModel(e.target.value)} />
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
