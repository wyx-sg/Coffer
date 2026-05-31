// frontend/src/components/chat/useChatStream.ts
//
// Imperative driver for a single chat turn. It owns the *live* view of a
// conversation while a turn streams: the optimistic user message, the
// in-flight assistant message (text accumulating delta-by-delta), tool-call /
// tool-result rows, and any pending confirmation. The persisted history comes
// from useConversation(); this hook layers the streaming turn on top.
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { chatApi, streamMessage, type ChatStreamEvent, type MessageOut } from "@/lib/api/chat";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";

/** A tool call surfaced mid-turn, with its result once it lands. */
export interface LiveToolCall {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  ok: boolean | null;
  summary: string | null;
}

/** A confirmation the runtime is blocked on, awaiting approve/deny. */
export interface PendingConfirmation {
  id: string;
  tool: string;
  args: Record<string, unknown>;
}

interface ChatStreamState {
  /** Optimistic user message text for the turn in flight (null when idle). */
  pendingUserText: string | null;
  /** Accumulated assistant text for the turn in flight. */
  assistantText: string;
  toolCalls: LiveToolCall[];
  confirmation: PendingConfirmation | null;
  /** True from POST until the `done`/`error` event (or abort). */
  streaming: boolean;
  /** Terminal error for the turn, surfaced as an assistant-side error row. */
  error: { code: string; message: string } | null;
}

const IDLE: ChatStreamState = {
  pendingUserText: null,
  assistantText: "",
  toolCalls: [],
  confirmation: null,
  streaming: false,
  error: null,
};

export function useChatStream(conversationId: string, onTurnComplete: () => void) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [state, setState] = useState<ChatStreamState>(IDLE);
  const abortRef = useRef<AbortController | null>(null);
  // Snapshot the callback so send() doesn't need it in its dep list.
  const onCompleteRef = useRef(onTurnComplete);
  onCompleteRef.current = onTurnComplete;

  const handleEvent = useCallback((event: ChatStreamEvent) => {
    setState((prev) => {
      switch (event.type) {
        case "text_delta":
          return { ...prev, assistantText: prev.assistantText + event.text };
        case "tool_call":
          return {
            ...prev,
            toolCalls: [
              ...prev.toolCalls,
              { id: event.id, tool: event.tool, args: event.args, ok: null, summary: null },
            ],
          };
        case "tool_result":
          return {
            ...prev,
            toolCalls: prev.toolCalls.map((tc) =>
              tc.id === event.id ? { ...tc, ok: event.ok, summary: event.summary } : tc,
            ),
          };
        case "confirmation":
          return {
            ...prev,
            confirmation: { id: event.id, tool: event.tool, args: event.args },
          };
        case "error":
          return { ...prev, error: { code: event.code, message: event.message } };
        case "done":
          return prev;
      }
    });
  }, []);

  const send = useCallback(
    async (text: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setState({
        pendingUserText: text,
        assistantText: "",
        toolCalls: [],
        confirmation: null,
        streaming: true,
        error: null,
      });
      try {
        await streamMessage(conversationId, text, handleEvent, controller.signal);
      } catch (err) {
        // An abort (Stop) is expected; everything else is a real failure.
        if (controller.signal.aborted) {
          // Leave whatever streamed so far visible; just stop the spinner.
        } else {
          const code = err instanceof ApiError ? err.code : "INTERNAL_ERROR";
          setState((prev) => ({
            ...prev,
            error: { code, message: translateApiError(t, err) },
          }));
          toast.error(translateApiError(t, err));
        }
      } finally {
        abortRef.current = null;
        setState((prev) => ({ ...prev, streaming: false, confirmation: null }));
        // Refetch the persisted history so the turn settles into real messages.
        onCompleteRef.current();
      }
    },
    [conversationId, handleEvent, t, toast],
  );

  const stop = useCallback(async () => {
    try {
      await chatApi.stop(conversationId);
    } catch (err) {
      toast.error(translateApiError(t, err));
    }
    abortRef.current?.abort();
  }, [conversationId, t, toast]);

  const confirm = useCallback(
    async (approve: boolean) => {
      const pending = state.confirmation;
      if (!pending) return;
      setState((prev) => ({ ...prev, confirmation: null }));
      try {
        await chatApi.confirm(conversationId, { request_id: pending.id, approve });
      } catch (err) {
        toast.error(translateApiError(t, err));
      }
    },
    [conversationId, state.confirmation, t, toast],
  );

  /** Drop the live turn overlay (e.g. when switching conversations). */
  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState(IDLE);
  }, []);

  return { state, send, stop, confirm, reset };
}

/** Build the synthetic message rows for the in-flight turn (after persisted history). */
export function liveTurnMessages(state: ChatStreamState): MessageOut[] {
  const rows: MessageOut[] = [];
  if (state.pendingUserText !== null) {
    rows.push({
      id: "live-user",
      role: "user",
      content: state.pendingUserText,
      status: "complete",
      tool_calls: [],
      error: null,
      created_at: "",
    });
  }
  const hasAssistantContent =
    state.assistantText.length > 0 ||
    state.toolCalls.length > 0 ||
    state.error !== null ||
    state.streaming;
  if (hasAssistantContent) {
    rows.push({
      id: "live-assistant",
      role: "assistant",
      content: state.assistantText,
      status: state.error ? "failed" : state.streaming ? "streaming" : "complete",
      tool_calls: state.toolCalls.map((tc) => ({
        id: tc.id,
        tool: tc.tool,
        args_summary: summarizeArgs(tc.args),
        result_summary: tc.summary,
        confirmed: null,
      })),
      error: state.error ? { code: state.error.code, message: state.error.message } : null,
      created_at: "",
    });
  }
  return rows;
}

/** A compact one-line preview of a tool-call's argument object. */
export function summarizeArgs(args: Record<string, unknown>): string {
  try {
    const json = JSON.stringify(args);
    return json.length > 200 ? `${json.slice(0, 200)}…` : json;
  } catch {
    return "";
  }
}
