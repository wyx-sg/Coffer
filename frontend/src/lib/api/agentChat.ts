// frontend/src/lib/api/agentChat.ts — transcript distillation endpoints for
// /api/v1/agents/{name}/transcripts* (Spec 007 extension, Task 12).
// Split from agents.ts for file-size; reuses the shared call/enc helpers.

import { call, enc } from "./agents";

// ---------------------------------------------------------------------------
// Wire types — mirror backend schemas.py
// ---------------------------------------------------------------------------

export interface TranscriptSessionSummary {
  session_id: string;
  project_path: string | null;
  message_count: number;
  started_at: string | null;
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
  type: string; // "decision" | "gotcha" | "convention" | "todo"
}

export interface DistillResponse {
  insights: InsightOut[];
  fact_ids: string[];
}

// ---------------------------------------------------------------------------
// Request functions
// ---------------------------------------------------------------------------

export function listTranscripts(
  agentName: string,
  opts: { limit?: number; offset?: number } = {},
): Promise<TranscriptSessionListResponse> {
  const limit = opts.limit ?? 100;
  const offset = opts.offset ?? 0;
  return call<TranscriptSessionListResponse>(
    "GET",
    `/agents/${enc(agentName)}/transcripts?limit=${limit}&offset=${offset}`,
  );
}

export function distillTranscript(
  agentName: string,
  body: DistillRequest,
): Promise<DistillResponse> {
  return call<DistillResponse>("POST", `/agents/${enc(agentName)}/transcripts/distill`, body);
}
