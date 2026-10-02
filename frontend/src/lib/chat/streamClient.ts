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
import { ApiError, daemonNotReadyError } from "../api/errors";
import type { components } from "../api/generated/chat";

// ---------------------------------------------------------------------------
// Event types
// ---------------------------------------------------------------------------

/** The `data:` payloads of the chat contract (`TurnEventMessage`), by their `type`. */
type TurnEventData = components["schemas"]["TurnEventMessage"];
type EventName = TurnEventData["type"];

/**
 * One event off the wire: the SSE `event:` name beside its `data:` payload, which
 * the contract types per name (each payload's `type` equals the name — spec chat
 * "Use the wire event name as the type discriminator"). Derived from the generated
 * schemas, so a field or an event the daemon adds, renames or drops changes this
 * union and every reader of it fails to compile.
 */
export type AgentEvent = {
  [E in EventName]: { event: E; data: Extract<TurnEventData, { type: E }> };
}[EventName];

/** SSE event names this client understands; anything else is skipped so the
 *  AgentEvent cast stays honest. Keyed by the contract's names, so adding or
 *  removing an event there is a compile error here until this client follows. */
const KNOWN_EVENTS: Record<EventName, true> = {
  turn_start: true,
  text_delta: true,
  tool_call: true,
  tool_result: true,
  turn_done: true,
  turn_error: true,
  queue_changed: true,
};

function isKnownEvent(name: string): name is EventName {
  return Object.hasOwn(KNOWN_EVENTS, name);
}

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
  const baseUrl = getCofferBaseUrl();
  // Nothing has named the API's address yet; see getCofferBaseUrl.
  if (baseUrl === null) throw daemonNotReadyError();
  const url = `${baseUrl}/chat/conversations/${conversationId}/events`;
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
        if (!isKnownEvent(frame.event)) continue;

        let parsed: unknown;
        try {
          parsed = JSON.parse(frame.data);
        } catch {
          // Skip non-JSON data lines (e.g. keep-alive comments).
          continue;
        }

        yield { event: frame.event, data: parsed } as AgentEvent;
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
      if (frame && isKnownEvent(frame.event)) {
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
