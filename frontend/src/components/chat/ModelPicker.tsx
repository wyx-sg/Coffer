// components/chat/ModelPicker.tsx
//
// Per-conversation model picker for a managed agent (the
// coffer-model-is-an-internal-engine and model-catalogue-read-from-the-agent ADRs). The
// value is `agent_config.model`, passed through to the agent's CLI. The picker
// is a FIXED dropdown — never free-text (spec provider-switching "Choose a
// model from a fixed list").
//
// Its options are the daemon's answer, plus the current value so it always
// stays selectable. Nothing else. `/agent-providers/{key}/models` serves
// `offered()`: the agent's own catalogue on its built-in login, or the active
// connection's curated ids when one is active — and it is the same function a
// channel's `/model` card reads, so the page and the chat cannot disagree.
//
// This component used to answer the question itself: it pulled every
// connection into the browser, found the active one, introspected its endpoint
// on first open, and offered the UNION of that and the agent's catalogue. The
// union was the bug. An active connection is projected into the agent's own
// config, so every turn goes to that endpoint — and the agent's own ids
// (`opus`, `sonnet`) do not exist there. The page offered models that would be
// rejected, the chat card offered the curated ones, and the page's list also
// changed depending on whether the endpoint happened to answer at that moment.
//
// It does NOT read the connection's stored `model`/`fast_model` (those left the
// connection: spec provider-switching "Take projected model keys from the
// agent's binding"). An empty value inherits the agent's projected default.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAgentModels } from "@/lib/hooks/useAgentModels";

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
  const offered = useAgentModels(agentKey);

  const suggestions = useMemo(() => {
    const out: Option[] = [];
    const seen = new Set<string>();
    const add = (id: string, label?: string) => {
      if (!id || seen.has(id)) return;
      seen.add(id);
      out.push({ id, label: label && label !== id ? label : undefined });
    };
    for (const m of offered.data ?? []) add(m.id, m.label);
    // Always keep the current value selectable, even when the daemon no longer
    // offers it — a model bound before the connection changed must not vanish
    // from the control that is displaying it.
    if (value) add(value);
    return out;
  }, [offered.data, value]);

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
