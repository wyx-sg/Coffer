// components/chat/ModelPicker.tsx
//
// Per-conversation model picker for a managed agent (ADR-024 → ADR-032 D4). The
// value is `agent_config.model`, passed through to the agent's CLI. The picker
// is a FIXED dropdown — never free-text (D4). Its options are state-dependent:
// when a connection overrides the agent, the connection's introspected models
// (fetched lazily on first open); otherwise the agent's curated built-in models.
// It does NOT read the connection's stored `model`/`fast_model` (those leave the
// connection in the E1 amendment); the current value is always shown so it stays
// selectable. An empty value inherits the agent's projected default. To pick a
// model outside this list, change the connection/binding on the Agent page.
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BUILTIN_MODELS_BY_AGENT, type AgentType } from "@/lib/api/providers";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

// Sentinel select value for "inherit the projected default". Real model ids are
// arbitrary strings; Radix forbids an empty-string item value, so this reserved
// token cannot realistically collide with a model id.
const INHERIT = "__inherit__";

interface Props {
  agentKey: string;
  /** The current per-conversation model override; null/"" → inherit the default. */
  value: string | null;
  /** Commit a new value (trimmed; "" → null). */
  onCommit: (model: string | null) => void;
  disabled?: boolean;
}

export function ModelPicker({ agentKey, value, onCommit, disabled = false }: Props) {
  const { t } = useTranslation();
  const [fetched, setFetched] = useState<string[]>([]);
  const introspected = useRef(false);

  // The picker is reused in place when the agent changes (draft selector swap,
  // or switching to a conversation bound to a different agent). Drop the
  // previous agent's introspected catalogue so its models don't leak into the
  // new agent's suggestions, and allow the new agent to be introspected.
  useEffect(() => {
    introspected.current = false;
    setFetched([]);
  }, [agentKey]);

  const providers = useProviders();
  const list = useListProviderModels();

  // The active connection for this agent is matched by its compatible-agents set
  // (not its wire), so a connection the user routed to this agent shows up even if
  // its endpoint speaks a different wire (the agnes case: an openai gateway →
  // Claude Code) — consistent with the Agent Overview picker.
  const activeConnection = useMemo(
    () =>
      (providers.data ?? []).find(
        (p) => p.compatible_agents.includes(agentKey as AgentType) && p.is_active,
      ) ?? null,
    [providers.data, agentKey],
  );

  const suggestions = useMemo(() => {
    const out: string[] = [];
    if (activeConnection) {
      // An override is active → the agent talks to the connection; offer the
      // models its endpoint lists (introspected). Built-in ids don't apply.
      for (const m of fetched) out.push(m);
    } else {
      // No override → the agent runs on its own login; offer its curated
      // built-in models (ADR-032 amendment D4).
      for (const m of BUILTIN_MODELS_BY_AGENT[agentKey] ?? []) out.push(m);
    }
    // Always keep the current value selectable, even when it is not in the list.
    if (value && !out.includes(value)) out.push(value);
    return out;
  }, [activeConnection, fetched, agentKey, value]);

  // Pull the connection's catalogue once, the first time the dropdown is opened.
  // Best-effort: a connection that can't list models just yields nothing.
  const introspect = () => {
    if (introspected.current || !activeConnection) return;
    introspected.current = true;
    list.mutate(
      {
        // Introspect with the connection's OWN wire (how to call its endpoint),
        // not the agent's — they can differ (the agnes case).
        provider: activeConnection.protocol,
        base_url: activeConnection.base_url,
        credential_ref: activeConnection.credential_ref,
      },
      { onSuccess: (r) => setFetched(r.models) },
    );
  };

  const commit = (next: string | null) => {
    const norm = next?.trim() || null;
    if (norm !== (value ?? null)) onCommit(norm);
  };

  const currentValue = value ?? "";
  const selectValue =
    currentValue !== "" && suggestions.includes(currentValue) ? currentValue : INHERIT;

  return (
    <Select
      disabled={disabled}
      value={selectValue}
      onValueChange={(v) => commit(v === INHERIT ? null : v)}
      onOpenChange={(open) => open && introspect()}
    >
      <SelectTrigger className="h-7 w-44 text-sm" aria-label={t("chat.modelPicker.label")}>
        <SelectValue placeholder={t("chat.modelPicker.placeholder")} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={INHERIT}>{t("chat.modelPicker.inheritNoModel")}</SelectItem>
        {suggestions.map((m) => (
          <SelectItem key={m} value={m}>
            {m}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
