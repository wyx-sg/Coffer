// src/lib/agents/hookRows.ts — the Hooks tab's rows and the state Coffer's own hook reads as.
//
// The listing (`GET /agents/{uid}/hooks`) gives every hook the agent's files
// declare plus Coffer's own hook's health, trust and last fire. The tab shows
// them in one table (spec agent-registry "List every hook in the agent's native
// config"): each declared hook is a row, owned by Coffer when it carries
// Coffer's marker, and a MISSING Coffer hook — which no file declares any more —
// becomes a row of its own so the tab can say so and offer Repair.
import type { StatusTone } from "@/components/status/statusTone";
import type { Owner } from "@/lib/agents/owner";
import type { AgentHooksOut, CofferHook, NativeHook } from "@/lib/api/agents";

export interface HookRow {
  key: string;
  owner: Owner;
  event: string;
  /** Null on the synthetic row of a missing Coffer hook. */
  command: string | null;
  matcher: string | null;
  path: string;
  /** The declaring plugin's id when a plugin's hook file declares it. */
  plugin: string | null;
  /** Coffer's hook state, on Coffer's rows only. */
  coffer: CofferHook | null;
}

export function hookRows(data: AgentHooksOut | undefined): HookRow[] {
  if (!data) return [];
  const cofferHook = data.coffer_hook;
  const rows: HookRow[] = data.items.map((h: NativeHook, i) => ({
    key: `${h.path}:${h.event}:${h.matcher ?? ""}:${h.command}:${i}`,
    owner: h.coffer ? "coffer" : "own",
    event: h.event,
    command: h.command,
    matcher: h.matcher,
    path: h.path,
    plugin: h.source === "plugin" ? h.plugin : null,
    coffer: h.coffer ? cofferHook : null,
  }));
  if (cofferHook?.health === "missing") {
    rows.unshift({
      key: `coffer-missing:${cofferHook.path}`,
      owner: "coffer",
      event: cofferHook.event,
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
  /** Hooks a file declares (a missing Coffer hook is not one). */
  hooks: number;
  files: number;
  coffer: number;
  own: number;
  cofferMissing: boolean;
}

export function hookSummaryCounts(data: AgentHooksOut | undefined): HookSummaryCounts {
  const items = data?.items ?? [];
  const coffer = items.filter((h) => h.coffer).length;
  return {
    hooks: items.length,
    files: new Set(items.map((h) => h.path)).size,
    coffer,
    own: items.length - coffer,
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

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

/** "2 hours ago" / "2小时前" — how long ago `iso` was, in the UI's language. */
export function timeAgo(iso: string, locale: string, now = Date.now()): string {
  const elapsed = now - new Date(iso).getTime();
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, ms] of UNITS) {
    if (Math.abs(elapsed) >= ms) return rtf.format(-Math.round(elapsed / ms), unit);
  }
  return rtf.format(0, "minute");
}
