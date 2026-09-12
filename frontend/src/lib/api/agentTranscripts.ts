// frontend/src/lib/api/agentTranscripts.ts — the read-only conversation list for
// /api/v1/agents/{name}/transcripts. Split from agents.ts for file-size; reuses
// the shared call/enc helpers exported from there.

import { call, enc } from "./agents";

// ---------------------------------------------------------------------------
// Wire types — mirror the backend's agent_transcript_routes.py schemas
// ---------------------------------------------------------------------------

export interface TranscriptSessionSummary {
  session_id: string;
  title: string | null;
  project_path: string | null;
  message_count: number;
  started_at: string | null;
  last_activity_at: string | null;
  /** Absolute path of the .jsonl file, so a row can open/reveal it. */
  source_path: string;
}

export type TranscriptSort = "started_at" | "last_activity_at" | "message_count";
export type SortOrder = "asc" | "desc";

export interface TranscriptListParams {
  limit?: number;
  offset?: number;
  /** Case-insensitive substring matched against title or project path. */
  q?: string;
  /** Filter to sessions whose project_path equals this exactly. */
  project?: string;
  sort?: TranscriptSort;
  order?: SortOrder;
}

export interface TranscriptSessionListResponse {
  sessions: TranscriptSessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

// ---------------------------------------------------------------------------
// Request functions
// ---------------------------------------------------------------------------

export function listTranscripts(
  agentName: string,
  opts: TranscriptListParams = {},
): Promise<TranscriptSessionListResponse> {
  const sp = new URLSearchParams();
  sp.set("limit", String(opts.limit ?? 100));
  sp.set("offset", String(opts.offset ?? 0));
  if (opts.q) sp.set("q", opts.q);
  if (opts.project) sp.set("project", opts.project);
  if (opts.sort) sp.set("sort", opts.sort);
  if (opts.order) sp.set("order", opts.order);
  return call<TranscriptSessionListResponse>(
    "GET",
    `/agents/${enc(agentName)}/transcripts?${sp.toString()}`,
  );
}
