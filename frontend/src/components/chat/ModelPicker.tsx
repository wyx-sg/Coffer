// components/chat/ModelPicker.tsx
//
// Per-conversation model picker for a managed agent (ADR-024 → ADR-032 D4). The
// value is `agent_config.model`, passed through to the agent's CLI. The picker
// is a FIXED dropdown — never free-text (D4). Its options are the UNION, deduped
// by id, of: the agent's own model catalogue from the daemon (curated aliases
// first, then ids discovered from the agent's config), the active connection's
// introspected models (fetched lazily on first open), and the current value so
// it always stays selectable. The union matters: a connection being active does
// not mean every chat runs through it, so hiding the agent's own models behind
// an active connection left real models unreachable. It does NOT read the
// connection's stored `model`/`fast_model` (those leave the connection in the E1
// amendment). An empty value inherits the agent's projected default.
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type AgentType } from "@/lib/api/providers";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

// Sentinel select value for "inherit the projected default". Real model ids are
// arbitrary strings; Radix forbids an empty-string item value, so this reserved
// token cannot realistically collide with a model id.
const INHERIT = "__inherit__";

/** One dropdown row. `id` is what the CLI receives; `label` is decoration only. */
interface Option {
  id: string;
  label?: string;
}

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
  const catalogue = useAgentModels(agentKey);

  // The active connection for this agent is matched by its compatible-agents set
  // (not its wire), so a connection the user routed to this agent shows up even if
  // its endpoint speaks a different wire (the agnes case: an openai gateway →
  // Claude Code) — consistent with the Agent Overview picker.
  const activeConnection = useMemo(
    () =>
      (providers.data ?? []).find(
        (p) => (p.compatible_agents ?? []).includes(agentKey as AgentType) && p.is_active,
      ) ?? null,
    [providers.data, agentKey],
  );

  const suggestions = useMemo(() => {
    const out: Option[] = [];
    const seen = new Set<string>();
    const add = (id: string, label?: string) => {
      if (!id || seen.has(id)) return;
      seen.add(id);
      out.push({ id, label: label && label !== id ? label : undefined });
    };
    // The agent's own catalogue first — the models it runs on its own login.
    for (const m of catalogue.data ?? []) add(m.id, m.label);
    // Then whatever the active connection's endpoint advertises.
    for (const m of fetched) add(m);
    // Always keep the current value selectable, even when it is in neither list.
    if (value) add(value);
    return out;
  }, [catalogue.data, fetched, value]);

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
    currentValue !== "" && suggestions.some((o) => o.id === currentValue) ? currentValue : INHERIT;

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
        {/* Lead with the display name when the catalogue supplies one: an id
            like `claude-opus-4-8` is unambiguous but unreadable at this width,
            and "Opus 4.8" is exactly the distinction the user needs to make. */}
        {suggestions.map((o) => (
          <SelectItem key={o.id} value={o.id}>
            {o.label ?? o.id}
            {o.label && <span className="ml-2 text-xs text-muted-foreground">{o.id}</span>}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
