// components/chat/MessageBubble.tsx
// One message of a conversation: the user's as a bubble on the right (with its
// files and, for a channel conversation, the not-delivered mark); the agent's as
// a column under its mark, name and time — text and tool-call cards in the order
// the turn emitted them, then the files it changed and its token counts.
// Memoised: a streaming turn re-renders the thread per token, and every
// already-persisted bubble keeps the same `message` reference across those.
import { memo } from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import type { ContentBlock, Message } from "@/lib/api/chat";
import type { LiveMessage } from "@/lib/hooks/useChatTurn";
import { messageText } from "@/lib/chat/mirror";
import { HelpTip } from "@/components/HelpTip";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { filesChanged } from "@/lib/conversations/filesChanged";
import { clock } from "@/lib/conversations/time";
import { FilesChangedCard } from "./FilesChangedCard";
import { AttachmentChip } from "./AttachmentChip";
import { ToolCallCard } from "./ToolCallCard";
import { ToolCallGroup, type ToolCall } from "./ToolCallGroup";
import { MarkdownContent } from "./MarkdownContent";

interface Props {
  message?: Message;
  live?: LiveMessage;
  /** For a user message the conversation's channel has not received yet: the
   *  platform's name (spec chat "Show where a reply will also be sent"). */
  undeliveredTo?: string;
  /** The conversation's agent, for the header over its replies. */
  agentKey?: string;
  agentName?: string;
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

/** Runs of this many consecutive tool calls fold into one group row. */
const GROUP_MIN = 3;

type Row =
  | { kind: "text"; key: string; text: string }
  | { kind: "tool"; key: string; call: ToolCall }
  | { kind: "group"; key: string; calls: ToolCall[] };

/** Fold each run of GROUP_MIN or more consecutive tool segments into one group. */
function groupSegments(segments: Segment[]): Row[] {
  const rows: Row[] = [];
  let run: ToolCall[] = [];
  const flush = () => {
    if (run.length >= GROUP_MIN)
      rows.push({ kind: "group", key: `group-${run[0].key}`, calls: run });
    else run.forEach((call) => rows.push({ kind: "tool", key: call.key, call }));
    run = [];
  };
  for (const seg of segments) {
    if (seg.kind === "tool") run.push({ key: seg.key, use: seg.use, result: seg.result });
    else {
      flush();
      rows.push(seg);
    }
  }
  flush();
  return rows;
}

function attachmentBlocks(blocks: ContentBlock[]): ContentBlock[] {
  return blocks.filter((b) => b.type === "attachment");
}

function MessageBubbleImpl({ message, live, undeliveredTo, agentKey, agentName }: Props) {
  const { t } = useTranslation();
  const isUser = message ? message.role === "user" : false;
  const isLive = live !== undefined;

  if (isUser && message) {
    const text = messageText(message.content);
    const attachments = attachmentBlocks(message.content);
    return (
      <div className="flex flex-col items-end gap-1">
        {text && (
          <div className="w-fit max-w-[min(48rem,100%)] whitespace-pre-wrap break-words rounded-xl bg-accent-soft px-3.5 py-2.5 text-sm leading-relaxed text-text">
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
        {undeliveredTo && (
          <div className="flex items-center gap-0.5 text-xs text-muted-foreground">
            <span>{t("conversations.mirror.notDelivered", { platform: undeliveredTo })}</span>
            <HelpTip>
              <p className="text-sm">{t("conversations.mirror.notDeliveredHelp")}</p>
            </HelpTip>
          </div>
        )}
      </div>
    );
  }

  // Assistant (persisted or live)
  const blocks = isLive ? live!.blocks : (message?.content ?? []);
  const segments = buildSegments(blocks);
  const rows = groupSegments(segments);
  const files = filesChanged(blocks);
  const failed = !isLive && message?.status === "failed";
  // A persisted streaming placeholder (turn still running server-side, seen
  // after a reload/switch-back) renders as in-progress, not as a blank bubble.
  const serverStreaming = !isLive && message?.status === "streaming";
  const promptTokens = message?.prompt_tokens;
  const completionTokens = message?.completion_tokens;
  const showTokens = !isLive && (promptTokens != null || completionTokens != null);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      {agentKey ? (
        <div className="flex items-center gap-2">
          <AgentBadge type={agentKey} name={agentName} size="sm" tooltip={false} />
          <span className="text-xs font-semibold text-text">{agentName}</span>
          {message ? (
            <time dateTime={message.created_at} className="text-2xs text-text-subtle">
              {clock(message.created_at)}
            </time>
          ) : null}
        </div>
      ) : null}
      <div className={cn("min-w-0 space-y-2.5", agentKey && "pl-[30px]")}>
        {rows.map((row, i) =>
          row.kind === "group" ? (
            <ToolCallGroup
              key={row.key}
              calls={row.calls}
              trailing={(isLive && live!.streaming && i === rows.length - 1) || serverStreaming}
            />
          ) : row.kind === "tool" ? (
            <ToolCallCard key={row.key} toolUse={row.call.use} toolResult={row.call.result} />
          ) : (
            <div key={row.key} className="text-sm leading-relaxed text-text">
              <MarkdownContent content={row.text} />
            </div>
          ),
        )}
        {((isLive && live!.streaming) || serverStreaming) && segments.length === 0 && (
          <div className="flex items-center gap-1 py-1 text-xs text-text-muted">
            <span className="animate-pulse">{t("conversations.thinking")}</span>
          </div>
        )}
        {failed && <p className="text-xs text-danger">{t("conversations.message.failed")}</p>}
        {!isLive || !live!.streaming ? <FilesChangedCard files={files} /> : null}
        {showTokens && (
          <p className="text-2xs text-text-subtle">
            {t("conversations.message.tokens", {
              prompt: formatTokens(promptTokens ?? 0),
              completion: formatTokens(completionTokens ?? 0),
            })}
          </p>
        )}
      </div>
    </div>
  );
}

/** 18234 → "18.2k": the header counts, not the invoice. */
function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

export const MessageBubble = memo(MessageBubbleImpl);
