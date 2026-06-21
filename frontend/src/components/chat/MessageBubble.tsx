// components/chat/MessageBubble.tsx
// Renders a single chat message (user or assistant) including tool call cards.
import { useTranslation } from "react-i18next";
import type { ContentBlock, Message } from "@/lib/api/chat";
import type { LiveMessage } from "@/lib/hooks/useChatTurn";
import { ToolCallCard } from "./ToolCallCard";
import { MarkdownContent } from "./MarkdownContent";

interface Props {
  message?: Message;
  live?: LiveMessage;
}

function buildToolPairs(blocks: ContentBlock[]): { use: ContentBlock; result?: ContentBlock }[] {
  const uses = blocks.filter((b) => b.type === "tool_use");
  const results = blocks.filter((b) => b.type === "tool_result");
  return uses.map((u) => ({
    use: u,
    result: results.find((r) => r.tool_use_id === u.tool_use_id),
  }));
}

function extractText(blocks: ContentBlock[]): string {
  return blocks
    .filter((b) => b.type === "text" && b.text)
    .map((b) => b.text)
    .join("");
}

export function MessageBubble({ message, live }: Props) {
  const { t } = useTranslation();
  const isUser = message ? message.role === "user" : false;
  const isLive = live !== undefined;

  if (isUser && message) {
    const text = extractText(message.content);
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-primary/10 px-4 py-2.5 text-sm text-foreground">
          {text}
        </div>
      </div>
    );
  }

  // Assistant (persisted or live)
  const text = isLive ? live!.text : extractText(message?.content ?? []);
  const toolBlocks = isLive ? live!.toolBlocks : (message?.content ?? []);
  const pairs = buildToolPairs(toolBlocks);
  const failed = !isLive && message?.status === "failed";
  // A persisted streaming placeholder (turn still running server-side, seen
  // after a reload/switch-back) renders as in-progress, not as a blank bubble.
  const serverStreaming = !isLive && message?.status === "streaming";
  const promptTokens = message?.prompt_tokens;
  const completionTokens = message?.completion_tokens;
  const showTokens = !isLive && (promptTokens != null || completionTokens != null);

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-1">
        {pairs.map((p) => (
          <ToolCallCard key={p.use.tool_use_id} toolUse={p.use} toolResult={p.result} />
        ))}
        {text && (
          <div className="rounded-2xl rounded-tl-sm bg-card px-4 py-2.5 text-sm text-foreground shadow-sm">
            <MarkdownContent content={text} />
          </div>
        )}
        {((isLive && live!.streaming) || serverStreaming) && !text && pairs.length === 0 && (
          <div className="flex items-center gap-1 px-4 py-2 text-xs text-muted-foreground">
            <span className="animate-pulse">{t("chat.thinking")}</span>
          </div>
        )}
        {failed && <p className="px-4 text-xs text-destructive">{t("chat.message.failed")}</p>}
        {showTokens && (
          <p className="px-4 text-xs text-muted-foreground">
            {t("chat.message.tokens", {
              prompt: promptTokens ?? 0,
              completion: completionTokens ?? 0,
            })}
          </p>
        )}
      </div>
    </div>
  );
}
