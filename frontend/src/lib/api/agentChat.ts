// frontend/src/lib/api/agentChat.ts — transcript distillation endpoints for
// /api/v1/agents/{name}/transcripts* (Spec 007 extension, Task 12).
// Split from agents.ts for file-size; reuses the shared call/enc helpers.

import { call, enc } from "./agents";

// ---------------------------------------------------------------------------
// Wire types — mirror backend schemas.py
// ---------------------------------------------------------------------------

export interface TranscriptSessionSummary {
  session_id: string;
  title: string | null;
  project_path: string | null;
  message_count: number;
  started_at: string | null;
  last_activity_at: string | null;
  source_path: string;
  /** done | never | queued | running | error — undefined on minimal apps. */
  distill_status?: string | null;
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
  /** ISO instant — keep sessions whose started_at is ≥ this. */
  startedAfter?: string;
  /** ISO instant — keep sessions whose started_at is ≤ this. */
  startedBefore?: string;
  sort?: TranscriptSort;
  order?: SortOrder;
}

export interface TranscriptSessionListResponse {
  sessions: TranscriptSessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface DistillRequest {
  session_id?: string;
  project_path?: string;
  model_id?: string;
  dry_run?: boolean;
}

export interface InsightOut {
  name: string;
  description: string;
  body: string;
}

export interface DistillResponse {
  insights: InsightOut[];
  journal_entries: string[];
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
  if (opts.startedAfter) sp.set("started_after", opts.startedAfter);
  if (opts.startedBefore) sp.set("started_before", opts.startedBefore);
  if (opts.sort) sp.set("sort", opts.sort);
  if (opts.order) sp.set("order", opts.order);
  return call<TranscriptSessionListResponse>(
    "GET",
    `/agents/${enc(agentName)}/transcripts?${sp.toString()}`,
  );
}

export function distillTranscript(
  agentName: string,
  body: DistillRequest,
): Promise<DistillResponse> {
  return call<DistillResponse>("POST", `/agents/${enc(agentName)}/transcripts/distill`, body);
}

export interface DistillBatchRequest {
  session_ids?: string[];
  /** Distil every session matching the filters below (select-all across pages). */
  all?: boolean;
  q?: string;
  project?: string;
  started_after?: string;
  started_before?: string;
}

export interface DistillBatchResponse {
  queued: number;
  skipped: number;
  total: number;
}

/** Enqueue async distillation for many sessions (returns immediately). */
export function distillBatch(
  agentName: string,
  body: DistillBatchRequest,
): Promise<DistillBatchResponse> {
  return call<DistillBatchResponse>(
    "POST",
    `/agents/${enc(agentName)}/transcripts/distill-batch`,
    body,
  );
}
