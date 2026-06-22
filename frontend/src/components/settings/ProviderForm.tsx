// components/settings/ProviderForm.tsx — add / edit an LLM connection (spec 011).
// A connection = endpoint + key + protocol. The model lives apart from the
// connection (amendment E1/E3) — chosen at the point of use — so the dialog has
// no model field. On create the user picks a PROVIDER preset (OpenAI, Anthropic,
// Google Gemini, Ollama, …) which fills the endpoint + protocol; "Custom" lets
// them enter any OpenAI-/Anthropic-compatible endpoint and pick the protocol by
// hand. In edit mode (`initial` set) name + protocol are fixed and the secret is
// optional — left blank, the stored key is kept.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { translateApiError } from "@/lib/api/errors";
import {
  wireNeedsCredential,
  type Protocol,
  type Provider,
  type ProviderCreate,
  type ProviderPatch,
} from "@/lib/api/providers";

interface Props {
  /** Present → edit an existing connection (name + protocol locked, secret optional). */
  initial?: Provider;
  submitError?: unknown;
  pending: boolean;
  onSubmit: (values: ProviderCreate) => Promise<void> | void;
  /** Required when `initial` is set; receives the PATCH body. */
  onUpdate?: (patch: ProviderPatch) => Promise<void> | void;
  onCancel: () => void;
}

interface Preset {
  id: string;
  label: string;
  protocol: Protocol | "";
  baseUrl: string;
}

// Built-in providers. Each fills the endpoint + protocol; "custom" leaves both
// to the user. OpenAI-compatible gateways (Gemini, DeepSeek, …) use the openai
// protocol — the agent compatibility is decided separately on the agent.
const PRESETS: Preset[] = [
  { id: "openai", label: "OpenAI", protocol: "openai", baseUrl: "https://api.openai.com/v1" },
  { id: "anthropic", label: "Anthropic", protocol: "anthropic", baseUrl: "https://api.anthropic.com" },
  {
    id: "gemini",
    label: "Google Gemini",
    protocol: "openai",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
  },
  { id: "deepseek", label: "DeepSeek", protocol: "openai", baseUrl: "https://api.deepseek.com" },
  { id: "moonshot", label: "Moonshot (Kimi)", protocol: "openai", baseUrl: "https://api.moonshot.cn/v1" },
  { id: "openrouter", label: "OpenRouter", protocol: "openai", baseUrl: "https://openrouter.ai/api/v1" },
  { id: "ollama", label: "Ollama", protocol: "ollama", baseUrl: "http://localhost:11434" },
  { id: "custom", label: "Custom", protocol: "", baseUrl: "" },
];

export function ProviderForm({ initial, submitError, pending, onSubmit, onUpdate, onCancel }: Props) {
  const { t } = useTranslation();
  const isEdit = initial != null;
  const [name, setName] = useState(initial?.name ?? "");
  const [presetId, setPresetId] = useState("openai");
  const [protocol, setProtocol] = useState<Protocol | "">(initial?.protocol ?? "openai");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "https://api.openai.com/v1");
  const [secret, setSecret] = useState("");

  const isCustom = presetId === "custom";
  const needsCredential = protocol === "" || wireNeedsCredential(protocol);

  // Picking a preset fills protocol + endpoint; custom clears them for hand entry.
  const pickPreset = (id: string) => {
    setPresetId(id);
    const preset = PRESETS.find((p) => p.id === id);
    if (preset && id !== "custom") {
      setProtocol(preset.protocol);
      setBaseUrl(preset.baseUrl);
    } else if (id === "custom") {
      setProtocol("openai");
      setBaseUrl("");
    }
  };

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (isEdit) {
          const patch: ProviderPatch = { base_url: baseUrl };
          if (needsCredential && secret) patch.secret_value = secret;
          await onUpdate?.(patch);
          return;
        }
        if (!protocol) return; // guard: a custom connection still needs a protocol
        const values: ProviderCreate = { name, protocol, base_url: baseUrl };
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

      {/* Provider preset (create only). Edit mode shows the locked protocol. */}
      {isEdit ? (
        <div className="space-y-1.5">
          <Label>{t("settings.connections.provider")}</Label>
          <p className="text-sm text-muted-foreground">{initial?.protocol}</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="p-preset">{t("settings.connections.provider")}</Label>
          <select
            id="p-preset"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={presetId}
            onChange={(e) => pickPreset(e.target.value)}
          >
            {PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id === "custom" ? t("settings.connections.customProvider") : p.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Custom connections pick the protocol by hand. */}
      {!isEdit && isCustom && (
        <div className="space-y-1.5">
          <Label htmlFor="p-wire">{t("settings.connections.wireFormat")}</Label>
          <select
            id="p-wire"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as Protocol)}
          >
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
            <option value="ollama">ollama</option>
          </select>
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="p-base">{t("settings.connections.baseUrl")}</Label>
        <Input
          id="p-base"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          required
        />
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

      {submitError != null && (
        <p className="text-sm text-destructive">{translateApiError(t, submitError)}</p>
      )}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={pending || (!isEdit && !protocol)}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
