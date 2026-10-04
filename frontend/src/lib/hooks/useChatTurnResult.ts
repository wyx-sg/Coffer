// The result shape of `useChatTurn`, split out so the hook file stays small.

import type { EchoAttachment, PendingEcho } from "@/lib/chat/echoes";
import type { LiveMessage } from "./chatTurnEvents";

/** @ui-only hook result; never crosses the wire. */
export interface UseChatTurnResult {
  /**
   * Send a message to the conversation (fire-and-return; never blocks), with the
   * composer's finished uploads. Resolves whether the daemon accepted it; a
   * refusal is also surfaced as `error`.
   */
  send: (text: string, attachments?: EchoAttachment[]) => Promise<boolean>;
  /** Send a persisted user message again, attachments included (Retry). */
  resend: (messageId: string) => Promise<boolean>;
  /** True while a turn is in flight on the subscription. */
  isStreaming: boolean;
  /** Live partial message — non-null while streaming (and briefly after). */
  liveMessage: LiveMessage | null;
  /**
   * Prompts this client sent whose persisted user rows have not been fetched
   * yet, in send order. The thread renders them after the fetched messages;
   * the hook retires each one when its row lands (see chatTurnEvents).
   */
  pendingEchoes: PendingEcho[];
  /** Latest error from a failed send/stream. */
  error: Error | null;
  /**
   * False when `error` is a refused send: that message never ran and stays in
   * the composer, so a Retry would re-send an older one.
   */
  retryable: boolean;
  /** Clear any error to allow a retry. */
  clearError: () => void;
  /** Stop the in-flight turn; its partial output is kept server-side. */
  interrupt: () => Promise<void>;
  /**
   * The queue is held: a queued message failed to START (a turn error that came
   * with no turn running, while messages wait). `error` says why; the action is
   * `resumeQueue`, not a Retry — the failed message was never persisted, so a
   * resend of the last user message would send the wrong one (spec chat "Hold a
   * queued turn that fails to start").
   */
  queueHeld: boolean;
  /** Resume a held queue: replace it with itself, which unpauses and advances it. */
  resumeQueue: () => Promise<void>;
  /** Queued messages waiting to run after the in-flight turn. */
  pending: string[];
  /** Replace the pending queue (resume / drop / reorder). */
  setPending: (texts: string[]) => Promise<void>;
  /** The stream dropped and every reconnect failed; a turn may still be running. */
  streamLost: boolean;
  /** Re-subscribe and refetch the messages — what the stream-lost banner's Reload does. */
  reload: () => void;
}
