// frontend/src/lib/reach/bulkReach.ts
//
// The arithmetic of a bulk reach change: for a selection of resources, which
// agent reaches how many of them, and what each resource's reach becomes when
// the user applies a mode (and, under Chosen agents, per-agent tick states).
// Pure functions — the popover draws them, `useBulkApply` writes them.
//
// A bulk write is a NEW INTENT, not an edit of one row's value, so nothing
// here starts from "the first row". Each agent's box is tri-state over the
// selection: ticked = every selected item reaches it, dash = some, empty =
// none. Clicking walks the states the selection can actually move to and ends
// back on the dash (as it was); an agent the user never touched ("orig") keeps
// whatever each item had.
//
// A chosen list is never empty: an enabled item the plan would leave with no
// agent is planned as Off instead (its scope kept), and the popover says so.
import type { Scope } from "@/lib/api/scope";
import { sameScope } from "@/lib/scope";
import type { ReachMode } from "@/lib/reach/reachState";
import type { ReachValue } from "@/lib/reach/useReachWrites";

/** What a bulk row has to carry: its identity, and the reach it has now. */
export interface BulkRow {
  kind: string;
  uid: string;
  /** Shown in the failure block; the uid stands in when absent. */
  name?: string;
  enabled: boolean;
  /** `null`/`undefined` = every agent. */
  scope?: Scope | null;
}

/** One agent's staged box: untouched, forced on for every item, forced off. */
export type AgentEdit = "orig" | "all" | "none";

export interface BulkPlan {
  mode: ReachMode | null;
  edits: Record<string, AgentEdit>;
}

/** Whether an item's reach, as it stands, includes this agent. */
function reaches(value: ReachValue | BulkRow, agentUid: string): boolean {
  if (!value.enabled) return false;
  const agents = value.scope?.agents ?? null;
  return agents === null || agents.includes(agentUid);
}

const currentOf = (row: BulkRow): ReachValue => ({
  enabled: row.enabled,
  scope: row.scope ?? null,
});

/** How many items reach this agent now. */
export function countNow(rows: BulkRow[], agentUid: string): number {
  return rows.filter((r) => reaches(r, agentUid)).length;
}

/** The reach one item ends up with, or `null` when the plan leaves it as it is. */
export function planRow(row: BulkRow, plan: BulkPlan, registered: string[]): ReachValue | null {
  const now = currentOf(row);
  if (plan.mode === "disabled") return now.enabled ? { ...now, enabled: false } : null;
  if (plan.mode === "everywhere") {
    return now.enabled && now.scope === null ? null : { enabled: true, scope: null };
  }
  if (plan.mode !== "restricted") return null;

  const edited = Object.values(plan.edits).some((e) => e !== "orig");
  if (!edited) return null;
  const kept = registered.filter((uid) => {
    const edit = plan.edits[uid] ?? "orig";
    return edit === "all" || (edit === "orig" && reaches(now, uid));
  });
  // Uids this machine does not know stay in the list — dropping one would
  // rewrite the item's scope behind the user's back.
  const unknown = (now.scope?.agents ?? []).filter((uid) => !registered.includes(uid));
  const agents = [...kept, ...unknown];
  if (now.enabled && now.scope === null && registered.every((uid) => agents.includes(uid))) {
    return null;
  }
  // A row left with nobody is off — a chosen list is never empty — and its
  // scope stays as it was, so turning it on again restores it.
  if (agents.length === 0) return now.enabled ? { ...now, enabled: false } : null;
  const next: Scope = { agents };
  return now.enabled && sameScope(now.scope, next) ? null : { enabled: true, scope: next };
}

/** How many items reach this agent once the plan is applied. */
export function countAfter(
  rows: BulkRow[],
  plan: BulkPlan,
  registered: string[],
  agentUid: string,
): number {
  return rows.filter((r) => reaches(planRow(r, plan, registered) ?? currentOf(r), agentUid)).length;
}

/** The states an agent's box walks through for this selection, in click order. */
function editCycle(now: number, total: number): AgentEdit[] {
  if (now === total) return ["orig", "none"];
  if (now === 0) return ["orig", "all"];
  return ["orig", "all", "none"];
}

export function nextEdit(edit: AgentEdit, now: number, total: number): AgentEdit {
  const cycle = editCycle(now, total);
  return cycle[(cycle.indexOf(edit) + 1) % cycle.length] ?? "orig";
}
