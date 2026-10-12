// src/lib/memory/syncFacts.ts — the Memory page's reading of the sync state's loosely typed parts.
//
// The state's `preview` and `last_report` are free-form objects on the wire
// (`sync_report.py` builds them: `preview_summary` and `SyncReport.summary`),
// so they are narrowed here, once, rather than at every component. Pure: no
// React, no i18n. Also the one table of how each copy state reads, and the
// project addresses the page and its detail share.
import type { MemorySyncState } from "@/lib/api/memoryTypes";
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
  /** Each memory the preview would write, update or remove there. */
  items: PreviewItem[];
}

/** @ui-only One memory of a preview row and what the preview does with its copy. */
interface PreviewItem {
  entry: string;
  title: string;
  action: "write" | "update" | "remove";
}

const ACTIONS = new Set(["write", "update", "remove"]);

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
    items: (Array.isArray(r.items) ? r.items : []).filter(isRecord).map((i) => ({
      entry: str(i.entry),
      title: str(i.title),
      action: (ACTIONS.has(str(i.action)) ? str(i.action) : "write") as PreviewItem["action"],
    })),
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

/** The `?scope=` of global memories, beside each project's hub folder. */
export const GLOBAL_SCOPE = "global";

/** A project's short name: the last segment of its key (`github.com/acme/payments` → `payments`). */
export function projectName(key: string): string {
  const parts = key.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? key;
}

/** The scope a page opens on when the URL names none: global memories when
 *  there are any, else the first project, else global (an empty hub). */
export function defaultScope(
  state: Pick<MemorySyncState, "projects" | "global_memories">,
): string {
  if (state.global_memories > 0) return GLOBAL_SCOPE;
  return state.projects[0]?.folder ?? GLOBAL_SCOPE;
}

/** The copy states that mean something needs a look: everything else (the
 *  origin, written, the rules file, Codex's own import, held back with its
 *  whole project) is how a copy normally is, and the list says nothing. */
const NOTABLE: readonly CopyState[] = ["pending", "edited", "removed"];

/** Per agent, the copy states a memory's row calls out. */
export function notableCopies(copies: Record<string, string>): [string, CopyState][] {
  return Object.entries(copies).flatMap(([agent, raw]) => {
    const state = copyState(raw);
    return state && NOTABLE.includes(state) ? [[agent, state] as [string, CopyState]] : [];
  });
}

/** How many memories the hub holds in all. */
export function totalMemories(
  state: Pick<MemorySyncState, "projects" | "global_memories">,
): number {
  return state.projects.reduce((n, p) => n + p.memories, state.global_memories);
}
