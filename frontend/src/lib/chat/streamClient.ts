// frontend/src/lib/chat/streamClient.ts
// SSE consumer for GET /api/v1/chat/conversations/{id}/events.
//
// Implements an async generator that yields typed AgentEvent objects parsed
// from the text/event-stream response. The subscription replays the in-flight
// turn then streams live, and stays open ACROSS turns (it does NOT close on
// turn_done). Handles:
//   - All SSE event names: turn_start, text_delta, tool_call, tool_result,
//     turn_done, turn_error, queue_changed
//   - Stream end (done: true from reader / abort signal)
//   - Network errors (fetch throws)
//   - HTTP error responses (non-200, e.g. 404 — JSON body)

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "../api/errors";

// ---------------------------------------------------------------------------
// Event types
// ---------------------------------------------------------------------------

export interface TurnStartEvent {
  event: "turn_start";
  // Backend TurnStarted dataclass has only `type`; no extra fields on the wire.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  data: {};
}

export interface TextDeltaEvent {
  event: "text_delta";
  data: { text: string };
}

export interface ToolCallEvent {
  event: "tool_call";
  data: {
    tool_use_id: string;
    tool_name: string;
    tool_input: Record<string, unknown>;
  };
}

export interface ToolResultEvent {
  event: "tool_result";
  data: {
    tool_use_id: string;
    tool_name: string;
    output?: Record<string, unknown> | null;
    error?: string | null;
  };
}

export interface TurnDoneEvent {
  event: "turn_done";
  // Backend TurnDone: prompt_tokens, completion_tokens, stop_reason, type.
  data: {
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
    stop_reason: string;
  };
}

export interface TurnErrorEvent {
  event: "turn_error";
  data: { code: string; message: string };
}

export interface QueueChangedEvent {
  event: "queue_changed";
  data: { pending: string[] };
}

export type AgentEvent =
  | TurnStartEvent
  | TextDeltaEvent
  | ToolCallEvent
  | ToolResultEvent
  | TurnDoneEvent
  | TurnErrorEvent
  | QueueChangedEvent;

/** SSE event names this client understands; anything else is skipped so the
 *  AgentEvent union cast stays honest. */
const KNOWN_EVENTS: ReadonlySet<string> = new Set([
  "turn_start",
  "text_delta",
  "tool_call",
  "tool_result",
  "turn_done",
  "turn_error",
  "queue_changed",
]);

// ---------------------------------------------------------------------------
// SSE frame parser
// ---------------------------------------------------------------------------

interface SseFrame {
  event: string;
  data: string;
}

/**
 * Parse a single SSE block (one or more lines between blank-line separators)
 * into a frame. Returns null if the block is empty or malformed.
 */
function parseFrame(block: string): SseFrame | null {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (dataLines.length === 0) return null;
  return { event: eventName, data: dataLines.join("\n") };
}

// ---------------------------------------------------------------------------
// Stream reader
// ---------------------------------------------------------------------------

/**
 * Subscribe to GET /chat/conversations/{id}/events and yield AgentEvents as
 * they arrive from the SSE stream.
 *
 * The subscription replays the in-flight turn then streams live, and stays
 * open ACROSS turns — it does NOT return on `turn_done`/`turn_error`. The
 * generator ends only when the response stream closes or the abort signal
 * fires.
 *
 * Throws ApiError for HTTP errors (non-200 JSON responses, e.g. 404).
 * Throws Error for network/stream failures.
 */
export async function* subscribeConversationEvents(
  conversationId: string,
  signal?: AbortSignal,
): AsyncGenerator<AgentEvent, void, unknown> {
  const url = `${getCofferBaseUrl()}/chat/conversations/${conversationId}/events`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "text/event-stream",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    signal,
  });

  if (!response.ok) {
    // Non-200 responses (e.g. 404 conversation not found) return JSON.
    const payload = await response.json().catch(() => null);
    const err = payload?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `subscribe failed: ${response.status}`,
    );
  }

  if (!response.body) {
    throw new Error("subscribeConversationEvents: response body is null");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by double newlines (LF or CRLF).
      const parts = buffer.split(/\r?\n\r?\n/);
      // Keep the last (potentially incomplete) part in the buffer.
      buffer = parts.pop() ?? "";

      for (const block of parts) {
        const trimmed = block.trim();
        if (!trimmed) continue;

        const frame = parseFrame(trimmed);
        if (!frame) continue;

        // Skip unrecognized event names so the union cast stays honest.
        if (!KNOWN_EVENTS.has(frame.event)) continue;

        let parsed: unknown;
        try {
          parsed = JSON.parse(frame.data);
        } catch {
          // Skip non-JSON data lines (e.g. keep-alive comments).
          continue;
        }

        const event = { event: frame.event, data: parsed } as AgentEvent;
        yield event;
        // The subscription is long-lived: it does NOT terminate on turn_done
        // or turn_error. It ends only when the stream closes or it is aborted.
      }
    }

    // Flush any bytes the decoder buffered (e.g. a multi-byte char split
    // across the final chunk), then parse any remaining frame.
    buffer += decoder.decode();
    const trimmed = buffer.trim();
    if (trimmed) {
      const frame = parseFrame(trimmed);
      if (frame && KNOWN_EVENTS.has(frame.event)) {
        let parsed: unknown;
        try {
          parsed = JSON.parse(frame.data);
          yield { event: frame.event, data: parsed } as AgentEvent;
        } catch {
          // ignore
        }
      }
    }
  } finally {
    // Cancel the body so the socket is torn down on exit (abort, stream close,
    // or an abandoned generator), not left dangling. The server-side turn keeps
    // running on disconnect by design.
    await reader.cancel().catch(() => {});
  }
}
