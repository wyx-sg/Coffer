// src/lib/chat/echoes.ts
// The optimistic echo of a prompt this client just sent: shown as a user bubble
// until its persisted row lands, then retired against that row. Pure — the SSE
// reducer (lib/hooks/chatTurnEvents) and useChatTurn own when these run.

import type { ContentBlock, Message } from "@/lib/api/chat";

/**
 * A prompt this client sent whose persisted user row has not been fetched yet.
 * The thread renders it as a user bubble so the message is visible before the
 * next messages refetch lands.
 *
 * The wire carries no client-generated id (POST .../messages takes only `text`
 * and attachment ids, and `turn_start` carries nothing), so an echo cannot be
 * matched to its row by id. It is matched by text (and the attached files'
 * names) AND time AND ordering instead — see reconcileEchoes.
 */
export interface PendingEcho {
  /** Stable render key. */
  id: string;
  /** The text as sent; empty for a message that carries only attachments. */
  text: string;
  /**
   * The files sent with it, shown as chips on the echo. An attachment-only
   * message is persisted with a stand-in text this client never saw, so its row
   * is matched by these names instead.
   */
  attachments: EchoAttachment[];
  /** Client clock (ms since epoch) when the send was issued. */
  sentAt: number;
  /**
   * Highest `seq` this client had already fetched when the send was issued.
   * Only a row with a greater seq can claim the echo, so an identical prompt
   * already in the thread can never satisfy the new one.
   */
  afterSeq: number;
}

/**
 * A persisted user row claims an echo only when its `created_at` falls within
 * this long AFTER the echo's `sentAt`. Generous: the daemon persists the row
 * when the turn starts, which may wait on agent spawn. An echo the window has
 * passed is still dropped once its turn settles (turn_done / turn_error), so a
 * slow start never leaves a ghost bubble.
 */
export const ECHO_MATCH_WINDOW_MS = 60_000;
/**
 * How far BEFORE `sentAt` a row's `created_at` may land and still match. The
 * daemon is local, so server/client drift is small; this only absorbs it.
 */
const ECHO_CLOCK_SKEW_MS = 5_000;

/** What an echo keeps of an attached file: what its chip shows. */
export interface EchoAttachment {
  filename: string;
  mime: string;
}

let echoSerial = 0;

/** Build the echo for a send issued now, given the rows the client has fetched. */
export function createEcho(
  text: string,
  known: Message[],
  now: number = Date.now(),
  attachments: EchoAttachment[] = [],
): PendingEcho {
  const afterSeq = known.reduce((max, m) => Math.max(max, m.seq), -1);
  echoSerial += 1;
  return { id: `echo-${echoSerial}`, text, attachments, sentAt: now, afterSeq };
}

/** The echo as a user row's content: its text, then one block per file. */
export function echoContent(echo: PendingEcho): ContentBlock[] {
  return [
    ...(echo.text ? [{ type: "text" as const, text: echo.text }] : []),
    ...echo.attachments.map((a) => ({
      type: "attachment" as const,
      filename: a.filename,
      mime: a.mime,
    })),
  ];
}

function createdAtMs(row: Message): number | null {
  const t = Date.parse(row.created_at);
  return Number.isNaN(t) ? null : t;
}

function rowClaimsEcho(row: Message, echo: PendingEcho): boolean {
  if (row.role !== "user" || row.seq <= echo.afterSeq) return false;
  if (echo.text && !row.content.some((b) => b.type === "text" && b.text === echo.text)) {
    return false;
  }
  const rowFiles = row.content.filter((b) => b.type === "attachment").map((b) => b.filename);
  const echoFiles = echo.attachments.map((a) => a.filename);
  if (rowFiles.length !== echoFiles.length || rowFiles.some((f, i) => f !== echoFiles[i])) {
    return false;
  }
  const created = createdAtMs(row);
  // A row with no parseable timestamp cannot be placed in time; the seq rule
  // above still guards against an older identical prompt.
  if (created === null) return true;
  return (
    created >= echo.sentAt - ECHO_CLOCK_SKEW_MS && created <= echo.sentAt + ECHO_MATCH_WINDOW_MS
  );
}

/**
 * Drop every echo whose persisted user row is now in `messages`.
 *
 * Echoes are walked in send order and each row claims at most one echo, so two
 * identical consecutive prompts resolve against two distinct rows. Sends are
 * ordered, so once a row with seq S claims an echo, every later echo can only be
 * claimed by a row after S — the survivors carry that floor forward in
 * `afterSeq`, which keeps a later reconcile from re-matching the same row.
 * Returns the same array when nothing changed so a setState is a no-op.
 */
export function reconcileEchoes(echoes: PendingEcho[], messages: Message[]): PendingEcho[] {
  if (echoes.length === 0) return echoes;
  const claimed = new Set<string>();
  let floorSeq = -1;
  const remaining: PendingEcho[] = [];
  for (const echo of echoes) {
    const row = messages.find(
      (m) => !claimed.has(m.id) && m.seq > floorSeq && rowClaimsEcho(m, echo),
    );
    if (row) {
      claimed.add(row.id);
      floorSeq = row.seq;
    } else {
      remaining.push(echo.afterSeq < floorSeq ? { ...echo, afterSeq: floorSeq } : echo);
    }
  }
  return remaining.length === echoes.length ? echoes : remaining;
}
