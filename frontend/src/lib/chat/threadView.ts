// frontend/src/lib/chat/threadView.ts — what the message thread shows.
// The persisted messages, the live streaming bubble and a failed turn overlap;
// these pure helpers decide which persisted rows render and what a Retry
// re-sends, so the component only lays them out. (The optimistic echoes are
// the turn hook's — it retires each one when its persisted row lands.)
import type { Message } from "@/lib/api/chat";
import type { LiveMessage } from "@/lib/hooks/chatTurnEvents";
import type { EchoAttachment, PendingEcho } from "@/lib/chat/echoes";

/** The text blocks of a message, joined. */
export function textOf(m: Message): string {
  return m.content
    .filter((b) => b.type === "text" && b.text)
    .map((b) => b.text)
    .join("");
}

/**
 * Persisted rows to render. While the live bubble is shown, fetched streaming
 * rows are dropped — a mid-turn refetch (e.g. window refocus) must not
 * duplicate the in-progress reply. After a failed turn, an empty streaming
 * placeholder would still render as "Thinking…" beside the error, so it is
 * dropped too (one that already carries text stays).
 */
export function visibleThreadMessages(
  messages: Message[],
  liveMessage: LiveMessage | null,
  turnError: unknown,
): Message[] {
  return messages.filter((m) => {
    if (m.status !== "streaming") return true;
    if (liveMessage) return false;
    return !(turnError && !textOf(m));
  });
}

/**
 * What a Retry re-sends. The newest optimistic echo is sent again as it was — its
 * text and its files' upload ids — since its row has not landed; otherwise the
 * last persisted user message (the failed turn's prompt survives server-side) is
 * resent by id, and the daemon rebuilds it with its attachments. `null` when
 * there is nothing to resend.
 */
export type RetryTarget =
  | { kind: "send"; text: string; attachments: EchoAttachment[] }
  | { kind: "resend"; messageId: string };

export function retryTargetFor(
  visible: Message[],
  echo: PendingEcho | undefined,
): RetryTarget | null {
  if (echo) return { kind: "send", text: echo.text, attachments: echo.attachments };
  for (let i = visible.length - 1; i >= 0; i -= 1) {
    if (visible[i].role === "user") return { kind: "resend", messageId: visible[i].id };
  }
  return null;
}
