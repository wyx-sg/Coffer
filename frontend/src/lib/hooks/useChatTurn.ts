// frontend/src/lib/hooks/useChatTurn.ts
// Drives streamClient.ts and accumulates SSE agent events into a live
// assistant message for the Chat page to render.
//
// API:
//   const { send, isStreaming, liveMessage, error,
//           pendingApproval, submitApproval, interrupt } = useChatTurn(convId);
//
// `liveMessage` is non-null while a turn is in flight and cleared after the
// persisted message is loaded (via messages query invalidation on turn_done).
// `pendingApproval` is non-null while a turn is paused on a human-approval
// request — the platform capability; Coffer's built-in agent does not use it.

import { type Dispatch, type SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { streamChatTurn, type AgentEvent, type ApprovalRequestEvent } from "@/lib/chat/streamClient";
import { chatApi, type ContentBlock } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { CONVERSATIONS_KEY, messagesKey } from "./useConversations";

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

export interface LiveMessage {
  /** Partial accumulated text from text_delta events. */
  text: string;
  /** Tool call/result blocks accumulated during the turn. */
  toolBlocks: ContentBlock[];
  /** Whether the turn is still streaming. */
  streaming: boolean;
}

/** A turn paused awaiting a human allow/deny decision on a tool call. */
export type PendingApproval = ApprovalRequestEvent["data"];

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseChatTurnResult {
  /** Send a message to the conversation and start streaming. */
  send: (text: string) => Promise<void>;
  /** True while the SSE stream is open. */
  isStreaming: boolean;
  /** Live partial message — non-null while streaming (and briefly after). */
  liveMessage: LiveMessage | null;
  /** Latest error from a failed send/stream. */
  error: Error | null;
  /** Clear any error to allow a retry. */
  clearError: () => void;
  /** Non-null while the turn is paused on a human-approval request. */
  pendingApproval: PendingApproval | null;
  /** Answer the pending approval request; the paused turn then resumes. */
  submitApproval: (behavior: "allow" | "deny") => Promise<void>;
  /** Stop the in-flight turn; its partial output is kept server-side. */
  interrupt: () => Promise<void>;
}

export function useChatTurn(conversationId: string): UseChatTurnResult {
  const qc = useQueryClient();
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveMessage, setLiveMessage] = useState<LiveMessage | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);

  // Abort controller allows cancellation on unmount / conversation switch.
  const abortRef = useRef<AbortController | null>(null);

  // Bind turn state to the conversation it belongs to: when the active
  // conversation changes (or the hook unmounts), abort any in-flight stream
  // for the previous conversation and reset the visible turn state, so a
  // streaming message, lock, approval, or error never bleeds into another
  // thread (nor gets its interrupt/approval POSTed to the wrong conversation).
  useEffect(() => {
    setIsStreaming(false);
    setLiveMessage(null);
    setError(null);
    setPendingApproval(null);
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [conversationId]);

  const send = useCallback(
    async (text: string) => {
      if (isStreaming) return; // guard: one in-flight turn per conversation

      setError(null);
      setIsStreaming(true);
      setLiveMessage({ text: "", toolBlocks: [], streaming: true });
      setPendingApproval(null);

      const controller = new AbortController();
      abortRef.current = controller;
      // A continuation is stale once the hook moved on to another run or
      // another conversation (abortRef was replaced/cleared). Every setState
      // after an await is gated on this, so a slow tail of the previous
      // conversation's turn (e.g. the invalidateQueries refetch) can never
      // wipe the current conversation's live state.
      const isCurrent = () => abortRef.current === controller;

      try {
        const gen = streamChatTurn(conversationId, text, controller.signal);

        for await (const event of gen) {
          if (!isCurrent()) return;
          if (event.event === "approval_request") {
            // The turn paused — surface the request so the user can decide.
            setPendingApproval(event.data);
          } else {
            handleEvent(event, setLiveMessage);
          }
        }

        // Turn completed — invalidate the messages query so the persisted
        // message is fetched and liveMessage can be cleared.
        await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
        if (isCurrent()) setLiveMessage(null);
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        if (!isCurrent()) return;
        const wrapped =
          err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
        setError(wrapped);
        setLiveMessage((prev) => (prev ? { ...prev, streaming: false } : null));
      } finally {
        if (isCurrent()) {
          setIsStreaming(false);
          setPendingApproval(null);
        }
        // The first turn renames the conversation server-side (auto-title);
        // refresh the list whether the turn succeeded or failed.
        void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
      }
    },
    [conversationId, isStreaming, qc],
  );

  const submitApproval = useCallback(
    async (behavior: "allow" | "deny") => {
      const approval = pendingApproval;
      if (!approval) return;
      try {
        await chatApi.submitApproval(conversationId, {
          request_id: approval.request_id,
          behavior,
        });
        // Clear only the request we answered — a later turn may have raised a
        // fresh one in the meantime.
        setPendingApproval((cur) => (cur === approval ? null : cur));
      } catch (err) {
        // The decision did not reach the turn — keep the card so the user can
        // retry, and surface the failure.
        const wrapped =
          err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
        setError(wrapped);
      }
    },
    [conversationId, pendingApproval],
  );

  const interrupt = useCallback(async () => {
    try {
      await chatApi.interruptTurn(conversationId);
    } catch {
      // Best-effort: the turn may have already finished on its own.
    }
  }, [conversationId]);

  const clearError = useCallback(() => setError(null), []);

  return {
    send,
    isStreaming,
    liveMessage,
    error,
    clearError,
    pendingApproval,
    submitApproval,
    interrupt,
  };
}

// ---------------------------------------------------------------------------
// Event handler (pure function — easier to test independently)
// ---------------------------------------------------------------------------

function handleEvent(
  event: Exclude<AgentEvent, ApprovalRequestEvent>,
  setLiveMessage: Dispatch<SetStateAction<LiveMessage | null>>,
): void {
  switch (event.event) {
    case "turn_start":
      break;

    case "text_delta":
      setLiveMessage((prev) =>
        prev ? { ...prev, text: prev.text + event.data.text } : null,
      );
      break;

    case "tool_call": {
      const block: ContentBlock = {
        type: "tool_use",
        tool_use_id: event.data.tool_use_id,
        tool_name: event.data.tool_name,
        tool_input: event.data.tool_input,
      };
      setLiveMessage((prev) =>
        prev ? { ...prev, toolBlocks: [...prev.toolBlocks, block] } : null,
      );
      break;
    }

    case "tool_result": {
      const resultBlock: ContentBlock = {
        type: "tool_result",
        tool_use_id: event.data.tool_use_id,
        tool_name: event.data.tool_name,
        output: event.data.output ?? null,
        error: event.data.error ?? null,
      };
      setLiveMessage((prev) =>
        prev ? { ...prev, toolBlocks: [...prev.toolBlocks, resultBlock] } : null,
      );
      break;
    }

    case "turn_done":
      setLiveMessage((prev) => (prev ? { ...prev, streaming: false } : null));
      break;

    case "turn_error":
      // The turn_error event ends the generator, so the catch in send() won't
      // run — throw here to route the error through it.
      throw new ApiError(event.data.code, event.data.message);
  }
}
