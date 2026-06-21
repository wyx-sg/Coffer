// components/chat/ModelPicker.tsx
//
// Per-conversation model picker for a managed agent (ADR-024 → ADR-032). The
// value is `agent_config.model`, passed through to the agent's CLI, so any model
// id is valid. The picker is a real dropdown (shadcn Select) listing the agent's
// available models — the active connection's `model`/`fast_model` augmented
// (lazily, on first open) by connection model introspection. Because a model id
// is free-form, the dropdown also offers a "Custom…" option that reveals a
// free-text input for a non-listed id. An empty value inherits the active
// connection's projected default, shown as the inherit option / placeholder
// hint. Mirrors the channel `/model` command.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { WIRE_BY_AGENT } from "@/lib/api/providers";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

// Sentinel select values. Real model ids are arbitrary strings; Radix forbids an
// empty-string item value, so the inherit/custom sentinels are reserved tokens
// that cannot realistically collide with a model id.
const INHERIT = "__inherit__";
const CUSTOM = "__custom__";

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
  const listId = useId();
  const [fetched, setFetched] = useState<string[]>([]);
  const introspected = useRef(false);
  // True while the user is typing a custom (non-listed) id.
  const [customMode, setCustomMode] = useState(false);
  const [text, setText] = useState(value ?? "");

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
    setCustomMode(false);
  }, [agentKey]);

  const providers = useProviders();
  const list = useListProviderModels();

  const wire = WIRE_BY_AGENT[agentKey];
  const activeConnection = useMemo(
    () => (providers.data ?? []).find((p) => p.wire_format === wire && p.is_active) ?? null,
    [providers.data, wire],
  );

  const suggestions = useMemo(() => {
    const out: string[] = [];
    if (activeConnection?.model) out.push(activeConnection.model);
    if (activeConnection?.fast_model) out.push(activeConnection.fast_model);
    for (const m of fetched) if (!out.includes(m)) out.push(m);
    return out;
  }, [activeConnection, fetched]);

  // Pull the connection's full catalogue once, the first time the dropdown is
  // opened. Best-effort: a connection that can't list models just yields
  // nothing.
  const introspect = () => {
    if (introspected.current || !wire || !activeConnection) return;
    introspected.current = true;
    list.mutate(
      {
        provider: wire,
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

  const placeholder = activeConnection?.model
    ? t("chat.modelPicker.defaultHint", { model: activeConnection.model })
    : t("chat.modelPicker.placeholder");

  // The current value is a known suggestion → the dropdown selects it directly.
  // Otherwise (a custom id, or no models to list) fall back to the free-text
  // input so the value is always editable.
  const currentValue = value ?? "";
  const valueIsKnown = currentValue !== "" && suggestions.includes(currentValue);
  const showText = customMode || (currentValue !== "" && !valueIsKnown);

  // With no models to offer and no custom value, there is nothing to pick — go
  // straight to the free-text input (keeps the picker usable for connections
  // that can't introspect, and matches the channel `/model` free-text command).
  const noOptions = suggestions.length === 0;

  if (showText || noOptions) {
    // Free-text custom entry. The `list` attribute keeps assistive suggestions
    // available (and gives the field the `combobox` role rather than a plain
    // textbox, matching the original picker).
    return (
      <>
        <Input
          list={listId}
          value={text}
          disabled={disabled}
          aria-label={t("chat.modelPicker.label")}
          placeholder={placeholder}
          onFocus={introspect}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => commit(text)}
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

  const selectValue = valueIsKnown ? currentValue : INHERIT;

  return (
    <Select
      disabled={disabled}
      value={selectValue}
      onValueChange={(v) => {
        if (v === CUSTOM) {
          setText("");
          setCustomMode(true);
          return;
        }
        commit(v === INHERIT ? null : v);
      }}
      onOpenChange={(open) => open && introspect()}
    >
      <SelectTrigger className="h-7 w-44 text-sm" aria-label={t("chat.modelPicker.label")}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={INHERIT}>
          {activeConnection?.model
            ? t("chat.modelPicker.inherit", { model: activeConnection.model })
            : t("chat.modelPicker.inheritNoModel")}
        </SelectItem>
        {suggestions.map((m) => (
          <SelectItem key={m} value={m}>
            {m}
          </SelectItem>
        ))}
        <SelectItem value={CUSTOM}>{t("chat.modelPicker.custom")}</SelectItem>
      </SelectContent>
    </Select>
  );
}
