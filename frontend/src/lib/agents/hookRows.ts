// src/lib/agents/hookRows.ts — the Hooks tab's rows and the state Coffer's own hook reads as.
//
// The listing (`GET /agents/{uid}/hooks`) gives every hook the agent's files
// declare plus Coffer's own hook's health, trust and last fire. The tab shows
// them in one table (spec agent-registry "List every hook in the agent's native
// config"): each declared hook is a row, owned by Coffer when it carries
// Coffer's marker. Coffer's memory hook sits on several events with one command,
// so its entries in one file are ONE row listing every event it sits on — never
// one row per event, and never the events joined into one string. A MISSING
// Coffer hook — which no file declares any more — becomes a row of its own so the
// tab can say so and offer Repair.
import type { StatusTone } from "@/lib/statusTone";
import type { Owner } from "@/lib/agents/owner";
import type { AgentHooksOut, CofferHook, NativeHook } from "@/lib/api/agents";

export interface HookRow {
  key: string;
  owner: Owner;
  /** The row's event; on Coffer's grouped row, its events comma-joined (for search). */
  event: string;
  /** Every event the row's hook sits on: one for the agent's own hooks, each of
   * them on Coffer's memory hook. */
  events: string[];
  /** Null on the synthetic row of a missing Coffer hook. */
  command: string | null;
  matcher: string | null;
  path: string;
  /** The declaring plugin's id when a plugin's hook file declares it. */
  plugin: string | null;
  /** Coffer's hook state, on Coffer's rows only. */
  coffer: CofferHook | null;
}

/** The events a comma-joined label names ("PostToolUse,SessionStart"): sorted, once each. */
function splitEvents(label: string): string[] {
  return [
    ...new Set(
      label
        .split(",")
        .map((e) => e.trim())
        .filter(Boolean),
    ),
  ].sort();
}

/** The named matchers a group of entries carries, or null when none names one. */
function groupMatcher(hooks: NativeHook[]): string | null {
  const named = [...new Set(hooks.map((h) => h.matcher).filter((m): m is string => !!m))].sort();
  return named.length ? named.join(", ") : null;
}

export function hookRows(data: AgentHooksOut | undefined): HookRow[] {
  if (!data) return [];
  const cofferHook = data.coffer_hook;
  const rows: HookRow[] = [];
  // Coffer's entries, grouped by the file that declares them: one row per file.
  const cofferByPath = new Map<string, NativeHook[]>();
  data.items.forEach((h: NativeHook, i) => {
    if (h.coffer) {
      const group = cofferByPath.get(h.path);
      if (group) {
        group.push(h);
        return;
      }
      cofferByPath.set(h.path, [h]);
    }
    rows.push({
      key: h.coffer
        ? `coffer:${h.path}`
        : `${h.path}:${h.event}:${h.matcher ?? ""}:${h.command}:${i}`,
      owner: h.coffer ? "coffer" : "own",
      event: h.event,
      events: [h.event],
      command: h.command,
      matcher: h.matcher,
      path: h.path,
      plugin: h.source === "plugin" ? h.plugin : null,
      coffer: h.coffer ? cofferHook : null,
    });
  });
  for (const row of rows) {
    const group = row.owner === "coffer" ? cofferByPath.get(row.path) : undefined;
    if (!group) continue;
    row.events = splitEvents(group.map((h) => h.event).join(","));
    row.event = row.events.join(",");
    row.matcher = groupMatcher(group);
  }
  if (cofferHook?.health === "missing") {
    const events = splitEvents(cofferHook.event);
    rows.unshift({
      key: `coffer-missing:${cofferHook.path}`,
      owner: "coffer",
      event: events.join(","),
      events,
      command: null,
      matcher: null,
      path: cofferHook.path,
      plugin: null,
      coffer: cofferHook,
    });
  }
  return rows;
}

interface HookSummaryCounts {
  /** Hooks a file declares, Coffer's memory hook counted once per file however
   * many events it sits on (a missing Coffer hook is not one). */
  hooks: number;
  files: number;
  coffer: number;
  own: number;
  cofferMissing: boolean;
}

export function hookSummaryCounts(data: AgentHooksOut | undefined): HookSummaryCounts {
  const items = data?.items ?? [];
  const coffer = new Set(items.filter((h) => h.coffer).map((h) => h.path)).size;
  const own = items.filter((h) => !h.coffer).length;
  return {
    hooks: own + coffer,
    files: new Set(items.map((h) => h.path)).size,
    coffer,
    own,
    cofferMissing: data?.coffer_hook?.health === "missing",
  };
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
  /** `agents.hooksTab.state.<word>`. */
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

/** The last path segment, for "<plugin> · hooks.json". */
export function fileName(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export { timeAgo } from "@/lib/timeAgo";
