// frontend/src/lib/api/agentTranscripts.ts — the read-only conversation surfaces
// for /api/v1/agents/{uid}/transcripts: the browse list, and the single-session
// read behind one conversation's page. Split from agents.ts for file-size. Wire
// types are aliases of the agent-registry contract's schemas; transport via the shared `call`
// (.agents/frontend.md §4).
//
// The two are separate calls because the wire shapes are deliberately different:
// a listing of a thousand sessions carries no message text at all, and the body
// only ever travels for the one session a reader opened.

import { call, enc } from "@/lib/api/call";
import type { components, paths } from "@/lib/api/generated/agent-registry";

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

type Schemas = components["schemas"];

/** One session in the listing. `source_path` is the absolute path of the
 *  .jsonl file, so a row can open/reveal it. */
export type TranscriptSessionSummary = Schemas["TranscriptSessionSummary"];

type ListQuery = NonNullable<
  paths["/api/v1/agents/{uid}/transcripts"]["get"]["parameters"]["query"]
>;

export type TranscriptSort = NonNullable<ListQuery["sort"]>;
type SortOrder = NonNullable<ListQuery["order"]>;

/** @ui-only The listing's query as the page builds it; every field maps to a
 *  query parameter of the route. */
export interface TranscriptListParams {
  limit?: number;
  /** The previous page's `next_cursor`; omitted for the first page. */
  cursor?: string;
  /** Case-insensitive substring matched against title or project path. */
  q?: string;
  /** Filter to sessions whose project_path equals this exactly. */
  project?: string;
  sort?: TranscriptSort;
  order?: SortOrder;
}

/** The listing pages by cursor: `next_cursor` reads the page after this one
 *  and is null on the last page. */
export type TranscriptSessionListResponse = Schemas["TranscriptSessionListResponse"];

/** One conversational turn, already secret-scrubbed and capped server-side. */
export type TranscriptMessage = Schemas["TranscriptMessageOut"];

/** One session's summary plus a window of its turns; `message_count` counts
 *  the turns in the WHOLE file, not the length of `messages`. */
export type TranscriptSessionDetail = Schemas["TranscriptSessionDetailResponse"];

// ---------------------------------------------------------------------------
// Request functions
// ---------------------------------------------------------------------------

export function listTranscripts(
  agentUid: string,
  opts: TranscriptListParams = {},
): Promise<TranscriptSessionListResponse> {
  const sp = new URLSearchParams();
  sp.set("limit", String(opts.limit ?? 100));
  if (opts.cursor) sp.set("cursor", opts.cursor);
  if (opts.q) sp.set("q", opts.q);
  if (opts.project) sp.set("project", opts.project);
  if (opts.sort) sp.set("sort", opts.sort);
  if (opts.order) sp.set("order", opts.order);
  return call<TranscriptSessionListResponse>(
    `/agents/${enc(agentUid)}/transcripts?${sp.toString()}`,
  );
}

/** Read one session: its summary plus `limit` turns starting at `offset`.
 *
 * `sourcePath` is the absolute `source_path` the listing handed out, and the
 * server accepts nothing else — it must resolve inside that agent's own
 * sessions directory. A transcript runs to tens of megabytes, so the window is
 * the point rather than a convenience.
 */
export function readTranscriptSession(
  agentUid: string,
  sourcePath: string,
  opts: { limit?: number; offset?: number } = {},
): Promise<TranscriptSessionDetail> {
  const sp = new URLSearchParams({ path: sourcePath });
  sp.set("limit", String(opts.limit ?? 200));
  sp.set("offset", String(opts.offset ?? 0));
  return call<TranscriptSessionDetail>(
    `/agents/${enc(agentUid)}/transcripts/session?${sp.toString()}`,
  );
}
