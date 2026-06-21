// components/chat/ToolCallCard.tsx
// Inline expandable card correlating a tool_use block with its tool_result.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import { CodeView } from "@/components/preview/CodeView";
import type { ContentBlock } from "@/lib/api/chat";

interface Props {
  toolUse: ContentBlock;
  toolResult?: ContentBlock;
}

export function ToolCallCard({ toolUse, toolResult }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const hasResult = toolResult !== undefined;
  const isError = hasResult && !!toolResult.error;

  return (
    <div
      className={cn(
        "my-1 rounded-md border text-xs",
        isError ? "border-destructive/40 bg-destructive/5" : "border-border bg-muted/40",
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left font-medium transition-colors hover:bg-muted/60"
        aria-expanded={expanded}
        aria-label={t("chat.toolCard.toggleAria", { name: toolUse.tool_name })}
      >
        <Wrench className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate font-mono text-xs">
          {toolUse.tool_name ?? t("chat.toolCard.unknown")}
        </span>
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-xs font-medium uppercase tracking-wide",
            !hasResult
              ? "bg-muted text-muted-foreground"
              : isError
                ? "bg-destructive/10 text-destructive"
                : "bg-status-ok/10 text-status-ok",
          )}
        >
          {!hasResult
            ? t("chat.toolCard.running")
            : isError
              ? t("chat.toolCard.error")
              : t("chat.toolCard.done")}
        </span>
        {expanded ? (
          <ChevronDown className="size-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3.5 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="space-y-2 border-t border-border px-3 py-2">
          {toolUse.tool_input != null && (
            <div>
              <div className="mb-1 font-semibold text-muted-foreground">
                {t("chat.toolCard.input")}
              </div>
              <CodeView
                value={JSON.stringify(toolUse.tool_input, null, 2)}
                language="json"
                maxHeight="20rem"
                lineNumbers={false}
                ariaLabel={t("chat.toolCard.input")}
                className="bg-background"
              />
            </div>
          )}
          {hasResult && (
            <div>
              <div className="mb-1 font-semibold text-muted-foreground">
                {isError ? t("chat.toolCard.errorLabel") : t("chat.toolCard.result")}
              </div>
              <CodeView
                value={
                  isError ? (toolResult.error ?? "") : JSON.stringify(toolResult.output, null, 2)
                }
                language={isError ? "text" : "json"}
                maxHeight="20rem"
                lineNumbers={false}
                ariaLabel={isError ? t("chat.toolCard.errorLabel") : t("chat.toolCard.result")}
                className={cn(isError ? "bg-destructive/5 text-destructive" : "bg-background")}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
