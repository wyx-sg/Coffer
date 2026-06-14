// frontend/src/lib/api/history.ts — typed fetch helpers for /api/v1/history/*
// Hand-written wire types matching the ADR-022 cross-agent transcript history
// surface (search / browse / reindex). Mirrors chat.ts: a private `call<T>`
// helper carrying the X-Coffer-Token / X-Coffer-Actor headers, one exported
// `historyApi` object of thin wrappers.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** One scrubbed turn of a browsed session (read-only). */
export interface HistoryTurn {
  role: string;
  text: string;
}

/** Session metadata shared by the list and browse responses. */
export interface HistorySession {
  agent_type: string;
  session_id: string;
  project_path: string | null;
  started_at: string | null;
  title: string;
  message_count: number;
}

/** One full-text search hit across indexed transcripts. */
export interface HistoryHit {
  agent_type: string;
  session_id: string;
  project_path: string | null;
  started_at: string | null;
  title: string;
  snippet: string;
  score: number;
}

export interface HistorySearchOut {
  query: string;
  hits: HistoryHit[];
}

export interface HistorySessionListOut {
  sessions: HistorySession[];
}

export interface HistorySessionOut {
  session: HistorySession;
  turns: HistoryTurn[];
}

export interface HistoryReindexOut {
  indexed: number;
  unchanged: number;
  removed: number;
}

export interface HistoryResetOut {
  removed: number;
}

export interface HistorySearchOpts {
  agentType?: string;
  project?: string;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const historyApi = {
  /** Full-text search across all indexed agent transcripts. */
  search: (query: string, opts: HistorySearchOpts = {}) => {
    const params = new URLSearchParams({ q: query });
    if (opts.agentType) params.set("agent_type", opts.agentType);
    if (opts.project) params.set("project", opts.project);
    params.set("limit", String(opts.limit ?? 20));
    return call<HistorySearchOut>("GET", `/history/search?${params.toString()}`);
  },

  /** List the indexed sessions for one agent. */
  listSessions: (agent: string) =>
    call<HistorySessionListOut>("GET", `/history/sessions?agent=${encodeURIComponent(agent)}`),

  /** Browse one session's scrubbed turns (read-only). */
  browseSession: (agent: string, sessionId: string) =>
    call<HistorySessionOut>(
      "GET",
      `/history/session?agent=${encodeURIComponent(agent)}&session_id=${encodeURIComponent(sessionId)}`,
    ),

  /** Re-index transcripts (all agents, or one when `agent` is given). */
  reindex: (agent?: string) =>
    call<HistoryReindexOut>(
      "POST",
      agent ? `/history/reindex?agent=${encodeURIComponent(agent)}` : "/history/reindex",
    ),

  /** Drop the entire index. */
  reset: () => call<HistoryResetOut>("POST", "/history/reset"),
};
