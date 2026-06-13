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

export function listTranscripts(agentName: string): Promise<TranscriptSessionListResponse> {
  return call<TranscriptSessionListResponse>(
    "GET",
    `/api/v1/agents/${enc(agentName)}/transcripts`,
  );
}

export function distillTranscript(
  agentName: string,
  body: DistillRequest,
): Promise<DistillResponse> {
  return call<DistillResponse>("POST", `/api/v1/agents/${enc(agentName)}/transcripts/distill`, body);
}
