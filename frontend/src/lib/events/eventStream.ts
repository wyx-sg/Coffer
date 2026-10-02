// src/lib/events/eventStream.ts — the reader of the daemon-wide change feed, GET /api/v1/events.
//
// One Server-Sent Events stream for the whole daemon (spec resource-framework
// "Announce every change on one daemon-wide event stream"). It is gated by the
// token header, so it is read with `fetch` rather than `EventSource`, and it
// carries three events: `change` (an invalidation hint `{seq, kind, id,
// op}` — never the resource's state), `resync` (something may have been
// missed: refetch everything) and `heartbeat` (nothing changed).
//
// The reader keeps itself connected: when the stream ends or fails it waits
// and reconnects, sending the SSE id of the last `change` it saw as
// `Last-Event-ID`, so the daemon replays what was missed or says `resync`.
// The wait grows on repeated failures, so an offline daemon costs one request
// every few seconds, not a tight loop.
import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import type { components } from "@/lib/api/types";

type ChangeEvent = components["schemas"]["ChangeEventOut"];

/** @ui-only What the reader hands its listener: a parsed event, or a word about the connection. */
export type StreamMessage =
  | { type: "change"; change: ChangeEvent }
  | { type: "resync" }
  | { type: "heartbeat"; seq: number }
  | { type: "open" }
  | { type: "closed" };

/** @ui-only One parsed SSE block. */
export interface SseFrame {
  event: string;
  data: string;
  id: string | null;
}

/** One SSE block → its event name, data and id; null for a comment-only block. */
export function parseSseBlock(block: string): SseFrame | null {
  let event = "message";
  let id: string | null = null;
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n"), id };
}

/** A frame as the message the listener gets; null for anything unrecognised. */
export function frameToMessage(frame: SseFrame): StreamMessage | null {
  let payload: unknown;
  try {
    payload = JSON.parse(frame.data);
  } catch {
    return null;
  }
  if (typeof payload !== "object" || payload === null) return null;
  const body = payload as Record<string, unknown>;
  if (frame.event === "change" && typeof body.kind === "string") {
    return { type: "change", change: body as unknown as ChangeEvent };
  }
  if (frame.event === "resync") return { type: "resync" };
  if (frame.event === "heartbeat" && typeof body.seq === "number") {
    return { type: "heartbeat", seq: body.seq };
  }
  return null;
}

const MIN_RETRY_MS = 1_000;
const MAX_RETRY_MS = 15_000;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}

/**
 * Read one connection until it ends. Returns the SSE id of the last `change`
 * seen (or `lastId` unchanged).
 */
async function readOnce(
  lastId: string | null,
  onMessage: (message: StreamMessage) => void,
  signal: AbortSignal,
): Promise<{ lastId: string | null }> {
  const base = getCofferBaseUrl();
  // Nothing has named the API's address yet (the desktop shell's handshake
  // has not landed): not an error, just not yet.
  if (base === null) return { lastId };
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
  };
  if (lastId) headers["Last-Event-ID"] = lastId;
  const response = await fetch(`${base}/events`, { method: "GET", headers, signal });
  if (signal.aborted || !response.ok || !response.body) return { lastId };
  onMessage({ type: "open" });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let seen = lastId;
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const frame = parseSseBlock(block);
      if (!frame) continue;
      const message = frameToMessage(frame);
      if (!message) continue;
      if (message.type === "change" && frame.id) seen = frame.id;
      onMessage(message);
    }
  }
  return { lastId: seen };
}

/**
 * Stay subscribed to the change feed until `signal` aborts, calling
 * `onMessage` for every event and for each connection opening and closing.
 * Never throws: a failed connection is retried after a growing wait.
 */
export async function followDaemonEvents(
  onMessage: (message: StreamMessage) => void,
  signal: AbortSignal,
): Promise<void> {
  let lastId: string | null = null;
  let wait = MIN_RETRY_MS;
  while (!signal.aborted) {
    let opened = false;
    const relay = (message: StreamMessage) => {
      if (message.type === "open") opened = true;
      onMessage(message);
    };
    try {
      lastId = (await readOnce(lastId, relay, signal)).lastId;
    } catch {
      // A refused or dropped connection: retried below, never surfaced.
    }
    if (signal.aborted) break;
    if (opened) onMessage({ type: "closed" });
    // A stream that was live starts over from the short wait; repeated
    // refusals back off.
    wait = opened ? MIN_RETRY_MS : Math.min(wait * 2, MAX_RETRY_MS);
    await sleep(wait, signal);
  }
}
