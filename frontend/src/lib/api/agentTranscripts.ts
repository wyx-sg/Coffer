// frontend/src/lib/api/agentTranscripts.ts — the read-only conversation list for
// /api/v1/agents/{name}/transcripts. Split from agents.ts for file-size. Wire
// types from the agent-registry contract; transport via the shared `call`
// (agents/frontend.md §4).

import { call, enc } from "@/lib/api/call";
import type { components, operations } from "@/lib/api/generated/agent-registry";

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

/**
 * Hand-written rather than the contract's `TranscriptSession`: the contract
 * marks `title` / `project_path` / `started_at` / `last_activity_at` optional,
 * while the backend always sends them (null when unknown) and the table cells
 * take `string | null`.
 */
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

type ListQuery = NonNullable<operations["listAgentTranscripts"]["parameters"]["query"]>;

export type TranscriptSort = NonNullable<ListQuery["sort"]>;
export type SortOrder = NonNullable<ListQuery["order"]>;

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

/** `TranscriptSessionListOut` with the hand-written session row above. */
export type TranscriptSessionListResponse = Omit<
  components["schemas"]["TranscriptSessionListOut"],
  "sessions"
> & { sessions: TranscriptSessionSummary[] };

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
    `/agents/${enc(agentName)}/transcripts?${sp.toString()}`,
  );
}
