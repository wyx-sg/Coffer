// frontend/src/lib/chat/threadView.ts — what the message thread shows.
// The persisted messages, the live streaming bubble, the optimistic echo of
// the just-sent prompt and a failed turn all overlap; these pure helpers
// decide which rows render so the component only lays them out.
import type { Message } from "@/lib/api/chat";
import type { LiveMessage } from "@/lib/hooks/chatTurnEvents";

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
 * Optimistic echo of the just-sent prompt: shown until a refetch delivers the
 * persisted user message. Once the last visible row IS that user message, the
 * fetched row wins and the echo is suppressed.
 */
export function shouldShowEcho(visible: Message[], echoText: string | undefined): boolean {
  if (echoText === undefined) return false;
  const last = visible[visible.length - 1];
  return !(last?.role === "user" && textOf(last) === echoText);
}

/**
 * The message a Retry re-sends: the optimistic echo, else the last persisted
 * user message (the failed turn's prompt survives server-side). Empty when
 * there is nothing to resend.
 */
export function retryTextFor(visible: Message[], echoText: string | undefined): string {
  if (echoText !== undefined) return echoText;
  for (let i = visible.length - 1; i >= 0; i -= 1) {
    if (visible[i].role === "user") return textOf(visible[i]);
  }
  return "";
}
