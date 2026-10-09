// src/lib/agents/hookRows.ts — what the Hooks tab shows: the agent's own hooks.
//
// The listing (`GET /agents/{uid}/hooks`) gives every hook the agent's files
// declare (spec agent-registry "List every hook in the agent's native config").
// The agent's own hooks are one table, one row per declared hook. Coffer
// installs no hook of its own.
import type { AgentHooksOut, NativeHook } from "@/lib/api/agents";

/** The events the Event filter always offers, in the order the agent fires them. */
const HOOK_EVENTS = [
  "SessionStart",
  "UserPromptSubmit",
  "PreToolUse",
  "PostToolUse",
  "Stop",
  "Notification",
] as const;

/** The agent's own hooks: every declared hook, in file order. */
export function ownHooks(data: AgentHooksOut | undefined): NativeHook[] {
  return data?.items ?? [];
}

/** A hook's identity within the listing. */
export function hookKey(h: NativeHook): string {
  return `${h.path}:${h.event}:${h.group_index}:${h.hook_index}`;
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

/** The last path segment, for "<plugin> · hooks.json". */
export function fileName(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}
