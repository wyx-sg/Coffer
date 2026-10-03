// src/lib/agents/hookRows.ts — what the Hooks tab shows: Coffer's memory hook and the agent's own hooks.
//
// The listing (`GET /agents/{uid}/hooks`) gives every hook the agent's files
// declare plus Coffer's own hook's health, trust and last fire (spec
// agent-registry "List every hook in the agent's native config"). The tab splits
// it: Coffer's hook is one block of properties (its events are tags, never rows),
// and the agent's own hooks — everything a file declares that is not Coffer's —
// are one table, one row per declared hook.
import type { StatusTone } from "@/lib/statusTone";
import type { AgentHooksOut, CofferHook, NativeHook } from "@/lib/api/agents";

/** The events the Event filter always offers, in the order the agent fires them. */
const HOOK_EVENTS = [
  "SessionStart",
  "UserPromptSubmit",
  "PreToolUse",
  "PostToolUse",
  "Stop",
  "Notification",
] as const;

/** The agent's own hooks: every declared hook that is not Coffer's, in file order. */
export function ownHooks(data: AgentHooksOut | undefined): NativeHook[] {
  return (data?.items ?? []).filter((h) => !h.coffer);
}

/** A hook's identity within the listing. */
export function hookKey(h: NativeHook): string {
  return `${h.path}:${h.event}:${h.group_index}:${h.hook_index}`;
}

/** The events Coffer's hook sits on (or would sit on, when it is missing): sorted, once each. */
export function cofferEvents(hook: CofferHook): string[] {
  const events = hook.event
    .split(",")
    .map((e) => e.trim())
    .filter(Boolean);
  return [...new Set(events)].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

function rank(event: string): number {
  const i = (HOOK_EVENTS as readonly string[]).indexOf(event);
  return i === -1 ? HOOK_EVENTS.length : i;
}

/** The events of the Event filter: the six always, then any other event a file declares. */
export function filterEvents(hooks: readonly NativeHook[]): string[] {
  const extra = [...new Set(hooks.map((h) => h.event))]
    .filter((e) => !(HOOK_EVENTS as readonly string[]).includes(e))
    .sort();
  return [...HOOK_EVENTS, ...extra];
}

/** How many hooks sit in how many files. */
export function hookTotals(hooks: readonly NativeHook[]): { hooks: number; files: number } {
  return { hooks: hooks.length, files: new Set(hooks.map((h) => h.path)).size };
}

/** The JSON position of a hook in its file: `hooks.PreToolUse[0].hooks[1]`. */
export function hookEntryPath(h: NativeHook): string {
  return `hooks.${h.event}[${h.group_index}].hooks[${h.hook_index}]`;
}

type CofferHookStateWord =
  | "current"
  | "stale"
  | "missing"
  | "neverFired"
  | "untrusted"
  | "modified"
  | "disabled";

interface CofferHookState {
  /** `agents.hooks.state.<word>`. */
  word: CofferHookStateWord;
  tone: StatusTone;
  /** Repair (reinstalling through the Coffer connection) would fix it. */
  repair: boolean;
}

/**
 * The one state Coffer's hook reads as. Health first (an out-of-date or missing
 * hook needs Repair whatever the agent thinks of it), then whether the agent will
 * run it at all (Codex's trust), then whether it has ever fired.
 */
export function cofferHookState(hook: CofferHook): CofferHookState {
  if (hook.health === "missing") return { word: "missing", tone: "err", repair: true };
  if (hook.health === "stale") return { word: "stale", tone: "warn", repair: true };
  if (hook.trust === "untrusted") return { word: "untrusted", tone: "warn", repair: false };
  if (hook.trust === "modified") return { word: "modified", tone: "warn", repair: false };
  if (hook.trust === "disabled") return { word: "disabled", tone: "off", repair: false };
  if (!hook.last_fired_at) return { word: "neverFired", tone: "warn", repair: false };
  return { word: "current", tone: "ok", repair: false };
}

/**
 * Coffer's hook is in place and current, but the agent will not run it until the
 * user approves it (Codex's `/hooks`): never approved, or approved for an earlier
 * command (changed since trusted). The agent's header says Hook not approved.
 */
export function hookNotApproved(hook: CofferHook | null | undefined): boolean {
  return hook?.health === "current" && (hook.trust === "untrusted" || hook.trust === "modified");
}

/** The last path segment, for "<plugin> · hooks.json". */
export function fileName(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export { timeAgo } from "@/lib/timeAgo";
