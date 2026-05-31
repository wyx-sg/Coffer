// frontend/src/lib/api/chat.ts — typed fetch helpers for /api/v1/conversations/*
// (spec 008-builtin-agent-chat). Sending a message returns a Server-Sent Events
// stream; that lives in streamMessage() below since openapi-fetch / the JSON
// `call` helper can't model a streaming body. Everything else is plain JSON.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

export type ConversationStatus = "active" | "archived";

export interface ToolCallOut {
  id: string;
  tool: string;
  args_summary: string;
  result_summary: string | null;
  confirmed: boolean | null;
}

export type MessageRole = "user" | "assistant" | "tool";

export type MessageStatus = "streaming" | "complete" | "failed" | "canceled";

export interface MessageOut {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  tool_calls: ToolCallOut[];
  error: Record<string, unknown> | null;
  created_at: string;
}

export interface ConversationOut {
  id: string;
  target_ref: string;
  title: string | null;
  status: ConversationStatus;
  model_snapshot: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ConversationListOut {
  items: ConversationOut[];
}

export interface ConversationDetailOut {
  conversation: ConversationOut;
  messages: MessageOut[];
}

export interface CreateConversationIn {
  target_ref: string;
}

export interface RenameConversationIn {
  title: string;
}

export interface ConfirmIn {
  request_id: string;
  approve: boolean;
}

// --- streamed turn events (SSE `data:` payloads) ---------------------------

export interface TextDeltaEvent {
  type: "text_delta";
  text: string;
}

export interface ToolCallEvent {
  type: "tool_call";
  id: string;
  tool: string;
  args: Record<string, unknown>;
}

export interface ToolResultEvent {
  type: "tool_result";
  id: string;
  tool: string;
  ok: boolean;
  summary: string;
}

export interface ConfirmationEvent {
  type: "confirmation";
  id: string;
  tool: string;
  args: Record<string, unknown>;
}

export interface ErrorEvent {
  type: "error";
  code: string;
  message: string;
}

export interface DoneEvent {
  type: "done";
}

export type ChatStreamEvent =
  | TextDeltaEvent
  | ToolCallEvent
  | ToolResultEvent
  | ConfirmationEvent
  | ErrorEvent
  | DoneEvent;

function authHeaders(json: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
  };
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

async function call<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: authHeaders(true),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 204) {
    return undefined as unknown as T;
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
  return data as T;
}

// Conversation ids are interpolated into URL paths; encode them so an id with
// URL-significant characters can't malform or misroute the request.
const enc = encodeURIComponent;

export const chatApi = {
  list: (status?: ConversationStatus, limit = 50, offset = 0) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    return call<ConversationListOut>("GET", `/conversations?${params.toString()}`);
  },
  create: (body: CreateConversationIn) => call<ConversationOut>("POST", "/conversations", body),
  get: (id: string) => call<ConversationDetailOut>("GET", `/conversations/${enc(id)}`),
  rename: (id: string, body: RenameConversationIn) =>
    call<ConversationOut>("PATCH", `/conversations/${enc(id)}`, body),
  archive: (id: string) => call<ConversationOut>("POST", `/conversations/${enc(id)}/archive`),
  restore: (id: string) => call<ConversationOut>("POST", `/conversations/${enc(id)}/restore`),
  remove: (id: string) => call<void>("DELETE", `/conversations/${enc(id)}`),
  confirm: (id: string, body: ConfirmIn) =>
    call<void>("POST", `/conversations/${enc(id)}/confirm`, body),
  stop: (id: string) => call<void>("POST", `/conversations/${enc(id)}/stop`),
};

/**
 * POST a message and stream the runtime events.
 *
 * The repo deliberately avoids `@microsoft/fetch-event-source`; we read the
 * `text/event-stream` body with a `fetch()` + `ReadableStream` reader and parse
 * the `data: <json>` frames ourselves. Each parsed {@link ChatStreamEvent} is
 * delivered to `onEvent`. Pass an `AbortSignal` to cancel the read (the Stop
 * button aborts locally and also calls the `/stop` endpoint).
 */
export async function streamMessage(
  id: string,
  text: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(`${getCofferBaseUrl()}/conversations/${enc(id)}/messages`, {
    method: "POST",
    headers: { ...authHeaders(true), Accept: "text/event-stream" },
    body: JSON.stringify({ text }),
    signal,
  });

  // Pre-stream validation (404 / 409 / 422 / 503) maps to the normal error
  // envelope before any streaming body is committed.
  if (!r.ok) {
    const data = await r.json().catch(() => null);
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
  if (!r.body) {
    throw new ApiError("INTERNAL_ERROR", "missing response body");
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flushFrame = (frame: string) => {
    // An SSE frame may carry multiple `data:` lines; concatenate them.
    const dataLines = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    if (dataLines.length === 0) return;
    const payload = dataLines.join("\n");
    if (!payload) return;
    try {
      onEvent(JSON.parse(payload) as ChatStreamEvent);
    } catch {
      // Ignore frames that aren't valid JSON (e.g. comments / keep-alives).
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Frames are separated by a blank line.
      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        flushFrame(buffer.slice(0, sep));
        buffer = buffer.slice(sep + 2);
        sep = buffer.indexOf("\n\n");
      }
    }
    // Flush any trailing frame the stream ended without a blank line after.
    if (buffer.trim()) flushFrame(buffer);
  } finally {
    reader.releaseLock();
  }
}
