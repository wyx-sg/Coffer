// components/settings/ProviderForm.tsx — add / edit an LLM connection (spec provider-switching).
// A connection = endpoint + key + protocol. The model lives apart from the
// connection (amendment E1/E3) — chosen at the point of use — so the dialog has
// no model field. On create the user picks a PROVIDER preset (OpenAI, Anthropic,
// Google Gemini, Ollama, …) which fills the endpoint + protocol; "Custom" lets
// them enter any OpenAI-/Anthropic-compatible endpoint and pick the protocol by
// hand. In edit mode (`initial` set) the secret is optional — left blank, the
// stored key is kept.
//
// WHICH AGENTS the connection reaches is NOT a field here. It used to be a set
// of compatible-agents checkboxes writing a `compatible_agents` config key; that
// key is gone — the axis is now the resource's framework-level per-agent SCOPE
// (ADR per-agent-resource-scope), owned by the shared `ScopeControl` that the
// connection's table row and its detail header already render. Keeping a second
// control here would either duplicate that one or, as it briefly did, send a
// field the backend no longer reads and silently discard the user's choice. A
// new connection starts on its wire's default scope (`Kind.default_scope`), so
// the common case needs no input at all; the hint below says where to change it.
//
// The NAME is editable in edit mode, but it does NOT travel in the PATCH body:
// it is the connection's identity, not one of its settings, so it leaves as its
// own rename call — `onUpdate` hands the caller the new name alongside the
// patch and the caller sequences the two. That ordering is what makes a name
// collision fail before anything else has been written.
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
import { PRESETS } from "./connectionPresets";

interface Props {
  /** Present → edit an existing connection (protocol locked, secret optional). */
  initial?: Provider;
  submitError?: unknown;
  pending: boolean;
  onSubmit: (values: ProviderCreate) => Promise<void> | void;
  /** Required when `initial` is set. Receives the PATCH body plus, when the user
   *  changed it, the new NAME — which is a separate rename call, not a patch
   *  field. `null` means the name is unchanged. */
  onUpdate?: (patch: ProviderPatch, newName: string | null) => Promise<void> | void;
  onCancel: () => void;
}

export function ProviderForm({
  initial,
  submitError,
  pending,
  onSubmit,
  onUpdate,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const isEdit = initial != null;
  const [name, setName] = useState(initial?.name ?? "");
  const [presetId, setPresetId] = useState("openai");
  const [protocol, setProtocol] = useState<Protocol | "">(initial?.protocol ?? "openai");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "https://api.openai.com/v1");
  const [secret, setSecret] = useState("");

  const isCustom = presetId === "custom";
  const needsCredential = protocol === "" || wireNeedsCredential(protocol);

  // Picking a preset fills protocol + endpoint; custom clears the endpoint for
  // hand entry.
  const pickPreset = (id: string) => {
    setPresetId(id);
    const preset = PRESETS.find((p) => p.id === id);
    setProtocol(id === "custom" ? "openai" : (preset?.protocol ?? "openai"));
    setBaseUrl(id === "custom" ? "" : (preset?.baseUrl ?? ""));
  };

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (isEdit) {
          const patch: ProviderPatch = { base_url: baseUrl };
          if (protocol && protocol !== initial.protocol) patch.protocol = protocol;
          if (needsCredential && secret) patch.secret_value = secret;
          const renamed = name.trim();
          await onUpdate?.(patch, renamed && renamed !== initial.name ? renamed : null);
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
        <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} required />
        {isEdit ? (
          <p className="text-xs text-muted-foreground">{t("settings.connections.renameHint")}</p>
        ) : null}
      </div>

      {/* Provider preset (create only). In edit mode the wire itself is
          editable instead: the probe that guessed it can be wrong, and nothing
          keys off it — an endpoint that turns out to speak a different wire is
          corrected here rather than recreated. */}
      {isEdit ? (
        <div className="space-y-1.5">
          <Label htmlFor="p-wire-edit">{t("settings.connections.wireFormat")}</Label>
          <select
            id="p-wire-edit"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as Protocol)}
          >
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
            <option value="ollama">ollama</option>
          </select>
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

      {/* Reach lives on the resource's scope, not in this dialog — the row's and
          the detail header's ScopeControl own it. Said here so the control's
          absence reads as a pointer rather than a missing field. */}
      <p className="text-xs text-muted-foreground">{t("settings.connections.reachHint")}</p>

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
