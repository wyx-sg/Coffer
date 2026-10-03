// The props of MessageThread, split out so the component file stays small.
import type { LiveMessage, PendingEcho } from "@/lib/hooks/useChatTurn";
import type { EchoAttachment } from "@/lib/chat/echoes";
import type { Conversation } from "@/lib/api/chat";
import type { ComposerRestore } from "@/lib/hooks/useComposerRestore";

export interface MessageThreadProps {
  conversation: Conversation;
  liveMessage: LiveMessage | null;
  /** Prompts sent from here whose rows have not landed yet (the turn hook retires them). */
  pendingEchoes?: PendingEcho[];
  isStreaming: boolean;
  /** Error from the latest turn (network, secret, agent error, …), and its dismiss. */
  turnError?: Error | null;
  onClearTurnError?: () => void;
  /** False when turnError is a refused send (it stays in the composer): no Retry. */
  retryable?: boolean;
  /** Send a persisted user message again, attachments included (Retry). */
  onResend?: (messageId: string) => void | Promise<boolean>;
  onStop?: () => void;
  /** Send a message with the finished uploads; resolves whether it was accepted. */
  onSend: (text: string, attachments?: EchoAttachment[]) => void | Promise<boolean>;
  /** A refused message handed back to the composer (see Composer `restore`). */
  restore?: ComposerRestore | null;
  onRestored?: () => void;
  /** Messages queued behind the in-flight turn, and its replacement (edit / remove). */
  pending?: string[];
  onSetPending?: (texts: string[]) => void;
  /** The queue is held after a queued message failed to start: the banner offers Resume, not Retry. */
  queueHeld?: boolean;
  onResumeQueue?: () => void;
  /** Display name of the conversation's agent — the composer's placeholder. */
  agentLabel?: string;
  /** The live stream was lost mid-turn after every reconnect: say so, offer Reload. */
  streamLost?: boolean;
  onReload?: () => void;
  /** Archived: read-only, an Unarchive in place of the composer. */
  readOnly?: boolean;
  onUnarchive?: () => void;
  unarchivePending?: boolean;
  /** A "Files changed" row was pressed (the diff drawer opens from it); `selectedPath` is the open one. */
  onOpenFile?: (path: string) => void;
  selectedPath?: string | null;
}
