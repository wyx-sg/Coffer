// components/chat/ModelPicker.tsx
//
// Per-conversation model picker for a managed agent (ADR-024 → ADR-032). A
// free-text combobox (Input + datalist) — the value is `agent_config.model`,
// passed through to the agent's CLI, so any model id is valid. Suggestions are
// best-effort: the agent's active provider profile model/fast_model, augmented
// (lazily, on first focus) by provider model introspection. An empty value
// inherits the global default the active provider profile projects, shown as the
// placeholder hint. Mirrors the channel `/model` command.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import type { WireFormat } from "@/lib/api/providers";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

/** Chat agent_key → provider wire format (ADR-032 projection targets). */
const WIRE_BY_AGENT: Record<string, WireFormat> = {
  claude_code: "anthropic",
  codex: "openai",
};

interface Props {
  agentKey: string;
  /** The current per-conversation model override; null/"" → inherit the default. */
  value: string | null;
  /** Commit a new value (trimmed; "" → null). Fired on blur / Enter. */
  onCommit: (model: string | null) => void;
  disabled?: boolean;
}

export function ModelPicker({ agentKey, value, onCommit, disabled = false }: Props) {
  const { t } = useTranslation();
  const listId = useId();
  const [text, setText] = useState(value ?? "");
  const [fetched, setFetched] = useState<string[]>([]);
  const introspected = useRef(false);

  // Re-sync when the override changes externally (switching conversations, or a
  // committed value arriving back through props).
  useEffect(() => setText(value ?? ""), [value]);

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

  const wire = WIRE_BY_AGENT[agentKey];
  const activeProfile = useMemo(
    () => (providers.data ?? []).find((p) => p.wire_format === wire && p.is_active) ?? null,
    [providers.data, wire],
  );

  const suggestions = useMemo(() => {
    const out: string[] = [];
    if (activeProfile?.model) out.push(activeProfile.model);
    if (activeProfile?.fast_model) out.push(activeProfile.fast_model);
    for (const m of fetched) if (!out.includes(m)) out.push(m);
    return out;
  }, [activeProfile, fetched]);

  // Pull the provider's full catalogue once, the first time the field is used.
  // Best-effort: a provider that can't list models just yields nothing.
  const onFocus = () => {
    if (introspected.current || !wire || !activeProfile) return;
    introspected.current = true;
    list.mutate(
      {
        provider: wire,
        base_url: activeProfile.base_url,
        credential_ref: activeProfile.credential_ref,
      },
      { onSuccess: (r) => setFetched(r.models) },
    );
  };

  const commit = () => {
    const next = text.trim() || null;
    if (next !== (value ?? null)) onCommit(next);
  };

  const placeholder = activeProfile?.model
    ? t("chat.modelPicker.defaultHint", { model: activeProfile.model })
    : t("chat.modelPicker.placeholder");

  return (
    <>
      <Input
        list={listId}
        value={text}
        disabled={disabled}
        aria-label={t("chat.modelPicker.label")}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onFocus={onFocus}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            (e.target as HTMLInputElement).blur();
          }
        }}
        className="h-7 w-44 text-sm"
      />
      <datalist id={listId}>
        {suggestions.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
    </>
  );
}
