// frontend/src/components/chat/ChatMessages.tsx
//
// The scrolling transcript: user / assistant bubbles, tool-call rows (with
// their result summary once it lands), per-message error rows, and the pending
// confirmation card. The confirmation card is rendered separately by the
// parent (it is conversation-scoped, not message-scoped) and passed in here so
// it sits at the bottom of the transcript.
import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2, Terminal, User } from "lucide-react";

import type { MessageOut, ToolCallOut } from "@/lib/api/chat";
import { cn } from "@/lib/utils";

function ToolCallRow({ call }: { call: ToolCallOut }) {
  const { t } = useTranslation();
  const settled = call.result_summary !== null;
  return (
    <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">
      <div className="flex items-center gap-2 font-medium text-foreground">
        <Terminal className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{call.tool}</span>
        {!settled ? (
          <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground" />
        ) : null}
      </div>
      {call.args_summary ? (
        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] text-muted-foreground">
          {call.args_summary}
        </pre>
      ) : null}
      {settled ? (
        <div className="mt-1 text-muted-foreground">
          <span className="font-medium text-foreground">{t("chat.toolResult")}:</span>{" "}
          {call.result_summary}
        </div>
      ) : null}
    </div>
  );
}

function MessageRow({ message }: { message: MessageOut }) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const errorMessage =
    message.error && typeof message.error.message === "string"
      ? (message.error.message as string)
      : null;

  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser ? (
        <div className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
          <Terminal className="size-4" strokeWidth={1.75} />
        </div>
      ) : null}
      <div className={cn("flex max-w-[80%] flex-col gap-2", isUser ? "items-end" : "items-start")}>
        {message.content ? (
          <div
            className={cn(
              "whitespace-pre-wrap break-words rounded-2xl px-4 py-2 text-sm",
              isUser
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-secondary-foreground",
            )}
          >
            {message.content}
            {message.status === "streaming" ? (
              <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-current align-middle" />
            ) : null}
          </div>
        ) : message.status === "streaming" && message.tool_calls.length === 0 ? (
          <div className="flex items-center gap-2 rounded-2xl bg-secondary px-4 py-2 text-sm text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            {t("chat.thinking")}
          </div>
        ) : null}

        {message.tool_calls.length > 0 ? (
          <div className="flex w-full flex-col gap-1.5">
            {message.tool_calls.map((call) => (
              <ToolCallRow key={call.id} call={call} />
            ))}
          </div>
        ) : null}

        {message.status === "canceled" ? (
          <div className="text-xs text-muted-foreground">{t("chat.canceled")}</div>
        ) : null}

        {errorMessage ? (
          <div
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-card px-3 py-2 text-xs text-destructive"
            role="alert"
          >
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
            <span className="break-words">{errorMessage}</span>
          </div>
        ) : null}
      </div>
      {isUser ? (
        <div className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
          <User className="size-4" strokeWidth={1.75} />
        </div>
      ) : null}
    </div>
  );
}

export function ChatMessages({
  messages,
  confirmationCard,
}: {
  messages: MessageOut[];
  /** The pending-confirmation card, rendered at the bottom of the transcript. */
  confirmationCard?: ReactNode;
}) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the newest content as the turn streams.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, confirmationCard]);

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6">
      {messages.length === 0 && !confirmationCard ? (
        <p className="m-auto text-sm text-muted-foreground">{t("chat.emptyConversation")}</p>
      ) : null}
      {messages.map((message) => (
        <MessageRow key={message.id} message={message} />
      ))}
      {confirmationCard}
      <div ref={bottomRef} />
    </div>
  );
}
