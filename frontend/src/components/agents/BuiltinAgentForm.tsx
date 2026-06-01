// frontend/src/components/agents/BuiltinAgentForm.tsx — spec 008.
// One modal form used for both creating and editing a built-in agent (kind
// `builtin_agent`). It edits BEHAVIOUR only — the LLM `model` + provider key
// (`credential_ref`) are GLOBAL and set in Settings → AI, so they are not
// fields here. On CREATE, the new agent inherits the default agent's `model` +
// `credential_ref` (passed in via `inheritFrom`). On edit it PATCHes the FULL
// merged config (the server replaces the whole object). The name is immutable
// post-create, so it shows read-only in edit mode.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { BuiltinAgentConfig, BuiltinAgentOut } from "@/lib/api/builtinAgents";
import { translateApiError } from "@/lib/api/errors";
import { useCreateBuiltinAgent, usePatchBuiltinAgent } from "@/lib/hooks/useBuiltinAgents";

// Local editable shape: every field is a string so empty inputs round-trip
// cleanly; we parse to the typed config only on submit. `model` +
// `credential_ref` are NOT edited here — they are carried through untouched.
interface FormState {
  name: string;
  system_prompt: string;
  temperature: string;
  max_tokens: string;
  use_gateway: boolean;
  confirm_tools: string;
}

function fromAgent(agent: BuiltinAgentOut | null): FormState {
  const c = agent?.config;
  return {
    name: agent?.name ?? "",
    system_prompt: c?.system_prompt ?? "",
    temperature: c?.temperature != null ? String(c.temperature) : "",
    max_tokens: c?.max_tokens != null ? String(c.max_tokens) : "",
    use_gateway: c?.use_gateway ?? true,
    // confirm_tools globs are edited one-per-line.
    confirm_tools: (c?.confirm_tools ?? []).join("\n"),
  };
}

// Build the full config object the server expects. `model` + `credential_ref`
// come from `base` (the agent being edited, or the inherited default on
// create). Optional fields are omitted when blank so we never send `""`/`NaN`
// (the schema forbids extras and types).
function toConfig(form: FormState, base: BuiltinAgentConfig): BuiltinAgentConfig {
  const config: BuiltinAgentConfig = { model: base.model };
  if (base.credential_ref) config.credential_ref = base.credential_ref;
  if (form.system_prompt.trim()) config.system_prompt = form.system_prompt;
  if (form.temperature.trim()) config.temperature = Number(form.temperature);
  if (form.max_tokens.trim()) config.max_tokens = Number(form.max_tokens);
  config.use_gateway = form.use_gateway;
  const tools = form.confirm_tools
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (tools.length > 0) config.confirm_tools = tools;
  return config;
}

export function BuiltinAgentForm(props: {
  // `null` => create mode; an agent => edit mode.
  agent: BuiltinAgentOut | null;
  // On create, the new agent inherits this config's `model` + `credential_ref`
  // (the default built-in agent's global provider config). Required for create;
  // ignored in edit mode (the edited agent's own config is the base).
  inheritFrom?: BuiltinAgentConfig | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const isEdit = props.agent !== null;
  const create = useCreateBuiltinAgent();
  const patch = usePatchBuiltinAgent();
  const [form, setForm] = useState<FormState>(() => fromAgent(props.agent));
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pending = create.isPending || patch.isPending;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    try {
      if (isEdit && props.agent) {
        const config = toConfig(form, props.agent.config);
        await patch.mutateAsync({ name: props.agent.name, config });
      } else {
        const name = form.name.trim();
        if (!name) {
          setErrorMsg(t("builtinAgents.errors.nameRequired"));
          return;
        }
        // Inherit the global model + provider key from the default agent.
        const base = props.inheritFrom;
        if (!base?.model) {
          setErrorMsg(t("builtinAgents.errors.modelRequired"));
          return;
        }
        const config = toConfig(form, base);
        await create.mutateAsync({ name, config });
      }
      props.onSaved();
    } catch (err) {
      setErrorMsg(translateApiError(t, err));
    }
  };

  return (
    <Dialog open onOpenChange={(next) => !next && props.onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? t("builtinAgents.editTitle") : t("builtinAgents.addTitle")}
          </DialogTitle>
          <DialogDescription>
            {isEdit ? t("builtinAgents.editSubtitle") : t("builtinAgents.addSubtitle")}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">
            {t("builtinAgents.name")}
            <Input
              className="mt-1"
              value={form.name}
              disabled={isEdit}
              readOnly={isEdit}
              placeholder={t("builtinAgents.namePlaceholder")}
              onChange={(e) => set("name", e.target.value)}
            />
          </label>

          {/* Model + provider key are global — set in Settings → AI, not here. */}
          <p className="text-xs text-muted-foreground">{t("builtinAgents.modelManagedHint")}</p>

          <label className="block text-sm">
            {t("builtinAgents.systemPrompt")}
            <textarea
              className="mt-1 block min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              value={form.system_prompt}
              placeholder={t("builtinAgents.systemPromptPlaceholder")}
              onChange={(e) => set("system_prompt", e.target.value)}
            />
          </label>

          <div className="flex gap-3">
            <label className="block flex-1 text-sm">
              {t("builtinAgents.temperature")}
              <Input
                className="mt-1"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={form.temperature}
                placeholder="0.7"
                onChange={(e) => set("temperature", e.target.value)}
              />
            </label>
            <label className="block flex-1 text-sm">
              {t("builtinAgents.maxTokens")}
              <Input
                className="mt-1"
                type="number"
                min={1}
                step={1}
                value={form.max_tokens}
                placeholder="4096"
                onChange={(e) => set("max_tokens", e.target.value)}
              />
            </label>
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <span className="text-sm">
              <span className="font-medium">{t("builtinAgents.useGateway")}</span>
              <span className="block text-xs text-muted-foreground">
                {t("builtinAgents.useGatewayHint")}
              </span>
            </span>
            <Switch
              checked={form.use_gateway}
              onCheckedChange={(v) => set("use_gateway", v)}
              aria-label={t("builtinAgents.useGateway")}
            />
          </div>

          <label className="block text-sm">
            {t("builtinAgents.confirmTools")}
            <textarea
              className="mt-1 block min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              value={form.confirm_tools}
              placeholder={t("builtinAgents.confirmToolsPlaceholder")}
              onChange={(e) => set("confirm_tools", e.target.value)}
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              {t("builtinAgents.confirmToolsHint")}
            </span>
          </label>

          {errorMsg ? (
            <p className="text-sm text-destructive" role="alert">
              {errorMsg}
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={props.onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? t("common.saving") : t("builtinAgents.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
