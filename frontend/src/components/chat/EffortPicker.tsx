// components/chat/EffortPicker.tsx
//
// Per-conversation reasoning-effort picker, sitting beside the model picker in
// the chat's model bar. The value is `agent_config.effort`.
//
// It lives next to ModelPicker rather than inside it because the two answer
// different questions and only one agent asks the second one. An effort is not
// part of a model NAME — Codex carries it as its own field on a turn — so it is
// a setting ON the chosen model, offered only when that model says it takes
// one. Claude Code's catalogue says no model of its does, so nothing renders
// for a Claude Code conversation and its bar looks exactly as it always has.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAgentModels } from "@/lib/hooks/useAgentModels";

// Same reserved token the model picker uses for "inherit"; Radix forbids an
// empty-string item value and no agent would name a level this.
const INHERIT = "__inherit__";

interface Props {
  agentKey: string;
  /** The conversation's model override; null → the agent runs its own default. */
  model: string | null;
  /** The current per-conversation effort override; null/"" → inherit. */
  value: string | null;
  /** Commit a new value (trimmed; "" → null). */
  onCommit: (effort: string | null) => void;
  disabled?: boolean;
}

export function EffortPicker({ agentKey, model, value, onCommit, disabled = false }: Props) {
  const { t } = useTranslation();
  const catalogue = useAgentModels(agentKey);

  // WHICH entry's levels apply. With a model chosen, its own catalogue entry
  // answers it outright. With none chosen the agent runs a default it never
  // names to us, so the catalogue's FIRST entry stands in — the backend hands
  // back the agent's own order, and the head of that order is what the agent
  // reaches for. That stand-in could only mislead for an agent whose catalogue
  // mixed effort-bearing and effort-free models, and neither agent does:
  // Codex's entries all carry levels, Claude Code's all carry none.
  const models = catalogue.data ?? [];
  const entry = (model ? models.find((m) => m.id === model) : models[0]) ?? null;
  const efforts = entry?.efforts ?? [];

  // Nothing to choose between → no control at all, not a disabled or empty one.
  if (efforts.length === 0) return null;

  const commit = (next: string | null) => {
    const norm = next?.trim() || null;
    if (norm !== (value ?? null)) onCommit(norm);
  };

  // Keep a stored level selectable even if the agent has since stopped offering
  // it, so the trigger never misreports what the conversation actually runs at.
  const options = value && !efforts.includes(value) ? [...efforts, value] : efforts;
  const selectValue = value && options.includes(value) ? value : INHERIT;

  return (
    <Select
      disabled={disabled}
      value={selectValue}
      onValueChange={(v) => commit(v === INHERIT ? null : v)}
    >
      <SelectTrigger className="h-7 w-32 text-sm" aria-label={t("chat.effortPicker.label")}>
        <SelectValue placeholder={t("chat.effortPicker.placeholder")} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={INHERIT}>
          {t("chat.effortPicker.inheritNoEffort")}
          {/* Naming the level the agent would pick makes "its own default" a
              fact the user can weigh, not a shrug. */}
          {entry?.default_effort && (
            <span className="ml-2 text-xs text-muted-foreground">{entry.default_effort}</span>
          )}
        </SelectItem>
        {/* Rendered verbatim: the levels are the agent's own vocabulary, and a
            translated or prettified "xhigh" would name something Codex does
            not, for no gain over the word it already chose. */}
        {options.map((e) => (
          <SelectItem key={e} value={e}>
            {e}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
