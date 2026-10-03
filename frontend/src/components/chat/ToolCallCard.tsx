// components/chat/ToolCallCard.tsx
// One tool call in an agent's reply: collapsed, its name, what it was called on
// (lib/conversations/toolSummary) and how it went — Running (muted, spinning),
// "Done · 0.3s", Error; a call with no result in a reply that was stopped or
// whose stream was lost reads "Stopped" / "Unknown" instead of Running;
// expanded, its input and its result (or error). A result is drawn only inside
// its own call's card.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import { Spinner } from "@/components/ui/spinner";
import { formatToolDuration } from "@/lib/format/duration";
import { CodeView } from "@/components/preview/CodeView";
import type { ContentBlock } from "@/lib/api/chat";
import { toolSummary } from "@/lib/conversations/toolSummary";
import { cn } from "@/lib/utils";

interface Props {
  toolUse: ContentBlock;
  toolResult?: ContentBlock;
  /** Why a call with no result is not running: its reply was stopped, or the live stream was lost. */
  unfinished?: "stopped" | "lost";
}

export function ToolCallCard({ toolUse, toolResult, unfinished }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const hasResult = toolResult !== undefined;
  const isError = hasResult && !!toolResult.error;
  const summary = toolSummary(toolUse.tool_input as Record<string, unknown> | null | undefined);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border bg-surface-raised text-xs",
        isError ? "border-danger/40" : "border-border-subtle",
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex h-9 w-full items-center gap-2.5 px-3 text-left transition-colors duration-fast hover:bg-surface-hover"
        aria-expanded={expanded}
        aria-label={t("conversations.toolCard.toggleAria", { name: toolUse.tool_name })}
      >
        <Wrench className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
        <span className="shrink-0 font-mono font-medium text-text">
          {toolUse.tool_name ?? t("conversations.toolCard.unknown")}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-text-muted">{summary}</span>
        {!hasResult ? (
          <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-text-muted">
            {unfinished ? null : <Spinner />}
            {unfinished === "stopped"
              ? t("conversations.toolCard.stopped")
              : unfinished === "lost"
                ? t("conversations.toolCard.lost")
                : t("conversations.toolCard.running")}
          </span>
        ) : isError ? (
          <StatusWord tone="err">{t("conversations.toolCard.error")}</StatusWord>
        ) : (
          <StatusWord tone="ok">
            {toolResult.duration_ms != null
              ? t("conversations.toolCard.doneIn", {
                  duration: formatToolDuration(toolResult.duration_ms),
                })
              : t("conversations.toolCard.done")}
          </StatusWord>
        )}
        {expanded ? (
          <ChevronDown className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
        ) : (
          <ChevronRight className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
        )}
      </button>

      {expanded && (
        <div className="space-y-2 border-t border-border-subtle px-3 py-2">
          {toolUse.tool_input != null && (
            <div>
              <div className="mb-1 font-semibold text-text-muted">
                {t("conversations.toolCard.input")}
              </div>
              <CodeView
                value={JSON.stringify(toolUse.tool_input, null, 2)}
                language="json"
                maxHeight="20rem"
                lineNumbers={false}
                ariaLabel={t("conversations.toolCard.input")}
                className="bg-background"
              />
            </div>
          )}
          {hasResult && (
            <div>
              <div className="mb-1 font-semibold text-text-muted">
                {isError
                  ? t("conversations.toolCard.errorLabel")
                  : t("conversations.toolCard.result")}
              </div>
              <CodeView
                value={
                  isError ? (toolResult.error ?? "") : JSON.stringify(toolResult.output, null, 2)
                }
                language={isError ? "text" : "json"}
                maxHeight="20rem"
                lineNumbers={false}
                ariaLabel={
                  isError
                    ? t("conversations.toolCard.errorLabel")
                    : t("conversations.toolCard.result")
                }
                className={cn(isError ? "bg-danger-soft text-danger" : "bg-background")}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
