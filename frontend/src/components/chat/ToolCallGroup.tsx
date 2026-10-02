// components/chat/ToolCallGroup.tsx
// A run of consecutive tool calls in an agent's reply, folded into one row
// ("Ran 12 tool calls") so a turn of dozens of shell commands does not bury its
// text. Collapsed by default; it opens by itself while a call in it is still
// running (or the turn is still streaming at it) and when one of them failed,
// and a click overrides either way. Each call keeps its own card inside.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Layers } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import type { ContentBlock } from "@/lib/api/chat";
import { ToolCallCard } from "./ToolCallCard";

export interface ToolCall {
  key: string;
  use: ContentBlock;
  result?: ContentBlock;
}

interface Props {
  calls: ToolCall[];
  /** The turn is still streaming and this is its last row: keep it open. */
  trailing?: boolean;
}

export function ToolCallGroup({ calls, trailing = false }: Props) {
  const { t } = useTranslation();
  const [override, setOverride] = useState<boolean | null>(null);
  const running = calls.some((c) => c.result === undefined);
  const failed = calls.filter((c) => c.result?.error).length;
  const open = override ?? (running || failed > 0 || trailing);

  return (
    <div data-testid="tool-call-group" className="space-y-2.5">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        aria-expanded={open}
        className="flex h-9 w-full items-center gap-2.5 rounded-lg border border-border-subtle bg-surface-raised px-3 text-left text-xs transition-colors duration-fast hover:bg-surface-hover"
      >
        <Layers className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-medium text-text">
          {t("conversations.tools.group", { count: calls.length })}
        </span>
        {running ? (
          <StatusWord tone="off">{t("conversations.toolCard.running")}</StatusWord>
        ) : failed > 0 ? (
          <StatusWord tone="err">{t("conversations.tools.failed", { count: failed })}</StatusWord>
        ) : null}
        {open ? (
          <ChevronDown className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
        ) : (
          <ChevronRight className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
        )}
      </button>
      {open && (
        <div className="space-y-2 border-l border-border-subtle pl-3">
          {calls.map((c) => (
            <ToolCallCard key={c.key} toolUse={c.use} toolResult={c.result} />
          ))}
        </div>
      )}
    </div>
  );
}
