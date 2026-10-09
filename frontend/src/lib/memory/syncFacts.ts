// src/lib/memory/syncFacts.ts — the Memory page's reading of the sync state's loosely typed parts.
//
// The state's `preview` and `last_report` are free-form objects on the wire
// (`sync_report.py` builds them: `preview_summary` and `SyncReport.summary`),
// so they are narrowed here, once, rather than at every component. Pure: no
// React, no i18n. Also the one table of how each copy state reads, and the
// project addresses the page and its detail share.
import type { MemorySyncState, SyncProject } from "@/lib/api/memoryTypes";
import type { StatusTone } from "@/lib/statusTone";

/** @ui-only One agent and project of a pending preview: how many copies it would write, update and remove. */
export interface PreviewRow {
  /** The agent type. */
  agent: string;
  /** The project key; `""` for global memories. */
  project: string;
  write: number;
  update: number;
  remove: number;
}

/** @ui-only A preview waiting for the person's Write or Cancel. */
export interface SyncPreview {
  createdAt: string;
  /** Every copy the preview would write, update or remove. */
  copies: number;
  rows: PreviewRow[];
}

/** @ui-only A source the last sync could not read, or a memory it withheld. */
export interface SourceProblem {
  agent: string;
  path: string;
  reason: string;
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** The pending preview, or `null` when there is none. */
export function parsePreview(raw: MemorySyncState["preview"]): SyncPreview | null {
  if (!isRecord(raw)) return null;
  const rows = (Array.isArray(raw.rows) ? raw.rows : []).filter(isRecord).map((r) => ({
    agent: str(r.agent),
    project: str(r.project),
    write: num(r.write),
    update: num(r.update),
    remove: num(r.remove),
  }));
  return { createdAt: str(raw.created_at), copies: num(raw.copies), rows };
}

function problems(raw: unknown): SourceProblem[] {
  return (Array.isArray(raw) ? raw : [])
    .filter(isRecord)
    .map((p) => ({ agent: str(p.agent), path: str(p.path), reason: str(p.reason) }));
}

/** The sources the last sync could not read: each agent contributed nothing from them. */
export function reportFailures(report: MemorySyncState["last_report"]): SourceProblem[] {
  return problems(report.failures);
}

/** The memories the last sync withheld because they looked like a secret (never their text). */
export function reportWithheld(report: MemorySyncState["last_report"]): SourceProblem[] {
  return problems(report.withheld);
}

/** @ui-only What one sync, write or undo did, as its toast counts it. */
export interface SyncSummary {
  published: number;
  updated: number;
  deleted: number;
  written: number;
  removed: number;
  /** The copies wait in a preview for the person's Write. */
  preview: boolean;
}

export function parseSummary(raw: Record<string, unknown>): SyncSummary {
  return {
    published: num(raw.published),
    updated: num(raw.updated),
    deleted: num(raw.deleted),
    written: num(raw.written),
    removed: num(raw.removed),
    preview: raw.preview === true,
  };
}

/** The copy states a hub entry has per local agent (`sync_view.py`, `sync_plan.py`). */
const COPY_STATES = [
  "origin",
  "written",
  "rules",
  "pending",
  "held_back",
  "deferred",
  "edited",
  "removed",
] as const;
export type CopyState = (typeof COPY_STATES)[number];

const COPY_TONE: Record<CopyState, StatusTone> = {
  // Written into the agent, as a copy or into Claude Code's rules file.
  written: "ok",
  rules: "ok",
  // Nothing to do, or the agent's own business: none of these is a problem.
  origin: "off",
  pending: "off",
  held_back: "off",
  deferred: "off",
  edited: "off",
  removed: "off",
};

/** A copy state the page knows, or `null` for one it does not (shown as written). */
export function copyState(raw: string | undefined): CopyState | null {
  return raw && (COPY_STATES as readonly string[]).includes(raw) ? (raw as CopyState) : null;
}

export function copyStateTone(state: CopyState): StatusTone {
  return COPY_TONE[state];
}

/** The URL segment of global memories, beside `/memory/projects/<folder>`. */
const GLOBAL_SEGMENT = "global";

/** Where a project's memories open: global memories have a fixed address, a project its hub folder. */
export function projectPath(project: Pick<SyncProject, "folder"> | null): string {
  return project
    ? `/memory/projects/${encodeURIComponent(project.folder)}`
    : `/memory/${GLOBAL_SEGMENT}`;
}

/** The address of a project known only by its key (a preview row), or the Memory page when it is not listed. */
export function projectPathByKey(projects: readonly SyncProject[], key: string): string | null {
  if (!key) return projectPath(null);
  const project = projects.find((p) => p.key === key);
  return project ? projectPath(project) : null;
}

/** How many memories the hub holds in all. */
export function totalMemories(
  state: Pick<MemorySyncState, "projects" | "global_memories">,
): number {
  return state.projects.reduce((n, p) => n + p.memories, state.global_memories);
}
