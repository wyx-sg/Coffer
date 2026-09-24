// components/chat/MessageBubble.tsx
// Renders a single chat message (user or assistant) including tool call cards.
// Memoised: a streaming turn re-renders the thread per token, and every
// already-persisted bubble keeps the same `message` reference across those.
import { memo } from "react";
import { useTranslation } from "react-i18next";
import type { ContentBlock, Message } from "@/lib/api/chat";
import type { LiveMessage } from "@/lib/hooks/useChatTurn";
import { AttachmentChip } from "./AttachmentChip";
import { ToolCallCard } from "./ToolCallCard";
import { MarkdownContent } from "./MarkdownContent";

interface Props {
  message?: Message;
  live?: LiveMessage;
}

type Segment =
  | { kind: "text"; key: string; text: string }
  | { kind: "tool"; key: string; use: ContentBlock; result?: ContentBlock };

/**
 * An assistant turn's blocks as render segments, in the order the turn emitted
 * them: each text block is its own segment (never glued to the next one), and
 * each tool call is a card at its call's position carrying its result, wherever
 * in the turn that result arrived. A result is drawn only inside its call's card.
 */
function buildSegments(blocks: ContentBlock[]): Segment[] {
  const results = blocks.filter((b) => b.type === "tool_result");
  const segments: Segment[] = [];
  blocks.forEach((b, i) => {
    if (b.type === "text" && b.text) {
      segments.push({ kind: "text", key: `text-${i}`, text: b.text });
    } else if (b.type === "tool_use") {
      segments.push({
        kind: "tool",
        key: b.tool_use_id ?? `tool-${i}`,
        use: b,
        result: results.find((r) => r.tool_use_id === b.tool_use_id),
      });
    }
  });
  return segments;
}

function extractText(blocks: ContentBlock[]): string {
  return blocks
    .filter((b) => b.type === "text" && b.text)
    .map((b) => b.text)
    .join("");
}

function attachmentBlocks(blocks: ContentBlock[]): ContentBlock[] {
  return blocks.filter((b) => b.type === "attachment");
}

function MessageBubbleImpl({ message, live }: Props) {
  const { t } = useTranslation();
  const isUser = message ? message.role === "user" : false;
  const isLive = live !== undefined;

  if (isUser && message) {
    const text = extractText(message.content);
    const attachments = attachmentBlocks(message.content);
    return (
      <div className="flex flex-col items-end gap-1">
        {text && (
          <div className="w-fit max-w-[min(48rem,100%)] whitespace-pre-wrap break-words rounded-xl rounded-tr-sm bg-primary/10 px-4 py-2.5 text-sm text-foreground">
            {text}
          </div>
        )}
        {attachments.length > 0 && (
          <div className="flex max-w-[min(48rem,100%)] flex-wrap justify-end gap-1.5">
            {attachments.map((a, i) => (
              <AttachmentChip
                key={`${a.filename ?? "file"}-${i}`}
                name={a.filename}
                detail={a.mime}
                mime={a.mime}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // Assistant (persisted or live)
  const segments = buildSegments(isLive ? live!.blocks : (message?.content ?? []));
  const failed = !isLive && message?.status === "failed";
  // A persisted streaming placeholder (turn still running server-side, seen
  // after a reload/switch-back) renders as in-progress, not as a blank bubble.
  const serverStreaming = !isLive && message?.status === "streaming";
  const promptTokens = message?.prompt_tokens;
  const completionTokens = message?.completion_tokens;
  const showTokens = !isLive && (promptTokens != null || completionTokens != null);

  return (
    <div className="flex justify-start">
      <div className="w-fit max-w-[min(48rem,100%)] space-y-1">
        {segments.map((seg) =>
          seg.kind === "tool" ? (
            <ToolCallCard key={seg.key} toolUse={seg.use} toolResult={seg.result} />
          ) : (
            <div
              key={seg.key}
              className="rounded-xl rounded-tl-sm bg-card px-4 py-2.5 text-sm text-foreground shadow-sm"
            >
              <MarkdownContent content={seg.text} />
            </div>
          ),
        )}
        {((isLive && live!.streaming) || serverStreaming) && segments.length === 0 && (
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

export const MessageBubble = memo(MessageBubbleImpl);
