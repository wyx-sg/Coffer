// components/settings/ProviderForm.tsx — add / edit an LLM connection (spec 011).
// A connection = endpoint + key + protocol. The model lives apart from the
// connection (amendment E1/E3) — chosen at the point of use — so the dialog has
// no model field. On create the user picks a PROVIDER preset (OpenAI, Anthropic,
// Google Gemini, Ollama, …) which fills the endpoint + protocol; "Custom" lets
// them enter any OpenAI-/Anthropic-compatible endpoint and pick the protocol by
// hand. The COMPATIBLE-AGENTS checkboxes decide which agents the connection
// projects into — pre-filled from the wire but editable, so an openai gateway can
// be routed to Claude Code. In edit mode (`initial` set) name + protocol are
// fixed and the secret is optional — left blank, the stored key is kept.
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
  type AgentType,
  type Protocol,
  type Provider,
  type ProviderCreate,
  type ProviderPatch,
} from "@/lib/api/providers";
import { PRESETS, SELECTABLE_AGENTS, defaultCompatibleAgents } from "./connectionPresets";

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

const AGENT_LABEL_KEY: Record<AgentType, string> = {
  claude_code: "settings.connections.agentClaudeCode",
  codex: "settings.connections.agentCodex",
};

export function ProviderForm({ initial, submitError, pending, onSubmit, onUpdate, onCancel }: Props) {
  const { t } = useTranslation();
  const isEdit = initial != null;
  const [name, setName] = useState(initial?.name ?? "");
  const [presetId, setPresetId] = useState("openai");
  const [protocol, setProtocol] = useState<Protocol | "">(initial?.protocol ?? "openai");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "https://api.openai.com/v1");
  const [secret, setSecret] = useState("");
  const [compatible, setCompatible] = useState<AgentType[]>(
    initial?.compatible_agents ?? defaultCompatibleAgents(initial?.protocol ?? "openai"),
  );

  const isCustom = presetId === "custom";
  const needsCredential = protocol === "" || wireNeedsCredential(protocol);
  // ollama is internal-only — it projects into no agent, so no checkboxes.
  const showCompatible = protocol !== "ollama";

  // Picking a preset fills protocol + endpoint and re-seeds the compatible agents
  // from the new wire; custom clears the endpoint for hand entry.
  const pickPreset = (id: string) => {
    setPresetId(id);
    const preset = PRESETS.find((p) => p.id === id);
    const nextProtocol = id === "custom" ? "openai" : (preset?.protocol ?? "openai");
    setProtocol(nextProtocol);
    setBaseUrl(id === "custom" ? "" : (preset?.baseUrl ?? ""));
    setCompatible(defaultCompatibleAgents(nextProtocol));
  };

  // Changing the custom wire re-seeds the default compatible agents for it.
  const pickCustomProtocol = (p: Protocol) => {
    setProtocol(p);
    setCompatible(defaultCompatibleAgents(p));
  };

  const toggleAgent = (a: AgentType) =>
    setCompatible((prev) => (prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]));

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (isEdit) {
          const patch: ProviderPatch = { base_url: baseUrl };
          if (needsCredential && secret) patch.secret_value = secret;
          if (showCompatible) patch.compatible_agents = compatible;
          await onUpdate?.(patch);
          return;
        }
        if (!protocol) return; // guard: a custom connection still needs a protocol
        const values: ProviderCreate = { name, protocol, base_url: baseUrl };
        if (needsCredential && secret) values.secret_value = secret;
        if (showCompatible) values.compatible_agents = compatible;
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
            onChange={(e) => pickCustomProtocol(e.target.value as Protocol)}
          >
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
            <option value="ollama">ollama</option>
          </select>
        </div>
      )}

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

      {showCompatible && (
        <div className="space-y-1.5">
          <Label>{t("settings.connections.compatibleAgents")}</Label>
          <div className="flex flex-wrap gap-3">
            {SELECTABLE_AGENTS.map((a) => (
              <label key={a} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={compatible.includes(a)}
                  onChange={() => toggleAgent(a)}
                />
                {t(AGENT_LABEL_KEY[a])}
              </label>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            {t("settings.connections.compatibleAgentsHint")}
          </p>
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
