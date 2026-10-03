// components/chat/MessageBubble.tsx
// One message of a conversation: the user's as a bubble on the right (with its
// files and, for a channel conversation, the not-delivered mark); the agent's as
// a column under its mark, name, time and state — text and tool-call cards in the
// order the turn emitted them, then (as the reply ended) the "Stopped by you."
// line, the files it changed, a failed-turn or lost-stream banner when it has
// one, and Copy reply with its token counts.
// Memoised: a streaming turn re-renders the thread per token, and every
// already-persisted bubble keeps the same `message` reference across those.
import { memo, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import type { ContentBlock, Message } from "@/lib/api/chat";
import type { LiveMessage } from "@/lib/hooks/useChatTurn";
import { messageText } from "@/lib/chat/mirror";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { filesChanged } from "@/lib/conversations/filesChanged";
import { replyText } from "@/lib/chat/replyText";
import { unfinishedWork } from "@/lib/chat/stopped";
import { ReplyFooter, ReplyStateText, StoppedLine, type ReplyState } from "./ReplyParts";
import { FilesChangedCard } from "./FilesChangedCard";
import { ThreadAttachment } from "./ThreadAttachment";
import { ToolCallCard } from "./ToolCallCard";
import { buildRows } from "@/lib/chat/replyRows";
import { ToolCallGroup } from "./ToolCallGroup";
import { MarkdownContent } from "./MarkdownContent";
import { QuestionCard } from "./QuestionCard";

interface Props {
  message?: Message;
  live?: LiveMessage;
  /** For a user message the conversation's channel has not received yet: the
   *  platform's name (spec chat "Show where a reply will also be sent"). */
  undeliveredTo?: string;
  /** The conversation's agent, for the header over its replies. */
  agentKey?: string;
  agentName?: string;
  /** The failed-turn or lost-stream banner, drawn inside this reply. */
  banner?: ReactNode;
  /** Set when `banner` explains what became of this reply, whatever its row says. */
  bannerState?: "failed" | "lost";
  /** A question is pending for the user (the header says "Waiting for you"). */
  waiting?: boolean;
  /** A "Files changed" row was pressed; `selectedPath` is the row whose diff is open. */
  onOpenFile?: (path: string) => void;
  selectedPath?: string | null;
}

function attachmentBlocks(blocks: ContentBlock[]): ContentBlock[] {
  return blocks.filter((b) => b.type === "attachment");
}

function replyStateOf(
  message: Message | undefined,
  live: LiveMessage | undefined,
  bannerState: Props["bannerState"],
  waiting: boolean,
): ReplyState {
  if (bannerState) return bannerState;
  if (live)
    return live.interrupted
      ? "stopped"
      : live.streaming
        ? waiting
          ? "waiting"
          : "running"
        : "done";
  if (message?.status === "streaming") return waiting ? "waiting" : "running";
  if (message?.status === "stopped") return "stopped";
  if (message?.status === "failed") return "failed";
  return "done";
}

function MessageBubbleImpl({
  message,
  live,
  undeliveredTo,
  agentKey,
  agentName,
  banner,
  bannerState,
  waiting = false,
  onOpenFile,
  selectedPath,
}: Props) {
  const { t } = useTranslation();
  const isUser = message ? message.role === "user" : false;
  const isLive = live !== undefined;

  if (isUser && message) {
    const text = messageText(message.content);
    const attachments = attachmentBlocks(message.content);
    return (
      <div className="flex flex-col items-end gap-1">
        {text && (
          <div className="w-fit max-w-[min(540px,100%)] whitespace-pre-wrap break-words rounded-xl bg-accent-soft px-3.5 py-2.5 text-sm leading-relaxed text-text">
            {text}
          </div>
        )}
        {attachments.length > 0 && (
          <div className="flex max-w-[min(540px,100%)] flex-wrap justify-end gap-1.5">
            {attachments.map((a, i) => (
              <ThreadAttachment
                key={`${a.attachment_id ?? a.filename ?? "file"}-${i}`}
                conversationId={message.conversation_id}
                block={a}
              />
            ))}
          </div>
        )}
        {undeliveredTo && (
          <p className="text-xs text-warning">
            {t("conversations.mirror.notDelivered", { platform: undeliveredTo })}
          </p>
        )}
      </div>
    );
  }

  // Assistant (persisted or live)
  const blocks = isLive ? live!.blocks : (message?.content ?? []);
  const rows = buildRows(blocks);
  const state = replyStateOf(message, live, bannerState, waiting);
  // A call with no result is running only while the reply is; after a stop it
  // was cut off, and after a lost stream or a failure the page cannot say.
  const unfinished =
    state === "running" || state === "waiting"
      ? undefined
      : state === "stopped"
        ? "stopped"
        : "lost";
  const working = state === "running" || state === "waiting";
  const promptTokens = message?.prompt_tokens;
  const completionTokens = message?.completion_tokens;
  const showTokens = !isLive && (promptTokens != null || completionTokens != null);
  const text = replyText(blocks);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      {agentKey ? (
        <div className="flex items-center gap-2">
          <AgentBadge type={agentKey} name={agentName} size="sm" tooltip={false} />
          <span className="text-xs font-semibold text-text">{agentName}</span>
          <ReplyStateText
            state={state}
            startedAt={live ? live.startedAt : message?.created_at}
            finishedAt={live ? live.endedAt : message?.finished_at}
          />
        </div>
      ) : null}
      <div className={cn("min-w-0 space-y-2.5", agentKey && "pl-[30px]")}>
        {rows.map((row, i) =>
          row.kind === "group" ? (
            <ToolCallGroup
              key={row.key}
              calls={row.calls}
              trailing={working && i === rows.length - 1}
              unfinished={unfinished}
            />
          ) : row.kind === "question" ? (
            <QuestionCard key={row.key} question={row.question} />
          ) : row.kind === "tool" ? (
            <ToolCallCard
              key={row.key}
              toolUse={row.call.use}
              toolResult={row.call.result}
              unfinished={unfinished}
            />
          ) : (
            <div key={row.key} className="text-sm leading-relaxed text-text">
              <MarkdownContent content={row.text} />
            </div>
          ),
        )}
        {working && rows.length === 0 && (
          <div className="flex items-center gap-1 py-1 text-xs text-text-muted">
            <span className="animate-pulse">{t("conversations.thinking")}</span>
          </div>
        )}
        {state === "stopped" && <StoppedLine unfinished={unfinishedWork(blocks)} />}
        {!working && (
          <FilesChangedCard
            files={filesChanged(blocks)}
            onOpenFile={onOpenFile}
            selectedPath={selectedPath}
          />
        )}
        {banner}
        {!working && state !== "lost" && (
          <ReplyFooter
            text={text}
            tokens={
              showTokens
                ? t("conversations.message.tokens", {
                    prompt: formatTokens(promptTokens ?? 0),
                    completion: formatTokens(completionTokens ?? 0),
                  })
                : null
            }
          />
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
