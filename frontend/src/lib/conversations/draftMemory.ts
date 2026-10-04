// src/lib/conversations/draftMemory.ts
// What the last New conversation used — the agent and the folders it worked in —
// remembered in this browser so the next draft opens on them. A per-viewer
// convenience: blocked or empty storage simply leaves the defaults (the first
// agent that can run, Coffer's own workspace).
import type { AgentProviderInfo } from "@/lib/api/agentProviders";

const DIRS_KEY = "coffer.conversations.recentWorkingDirs";
const LAST_DIR_KEY = "coffer.conversations.lastWorkingDir";
const AGENT_KEY = "coffer.conversations.lastAgent";
/** How many folders the workspace picker lists. */
export const MAX_RECENT_DIRS = 8;

/** Folders conversations were started in, most recent first. */
export function readRecentWorkingDirs(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(DIRS_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((d): d is string => typeof d === "string" && d !== "");
  } catch {
    return [];
  }
}

/** The folder the last conversation started in; null is Coffer's own workspace. */
export function readLastWorkingDir(): string | null {
  try {
    return localStorage.getItem(LAST_DIR_KEY) || null;
  } catch {
    return null;
  }
}

/** Record a started conversation's folder: it becomes the next default, and Coffer's
 *  workspace (null) is the default but not a folder to list. */
export function rememberWorkingDir(dir: string | null): void {
  try {
    localStorage.setItem(LAST_DIR_KEY, dir ?? "");
    if (!dir) return;
    const next = [dir, ...readRecentWorkingDirs().filter((d) => d !== dir)].slice(
      0,
      MAX_RECENT_DIRS,
    );
    localStorage.setItem(DIRS_KEY, JSON.stringify(next));
  } catch {
    // Blocked storage: nothing to remember, and nothing breaks.
  }
}

export function rememberAgent(agentKey: string): void {
  try {
    if (agentKey) localStorage.setItem(AGENT_KEY, agentKey);
  } catch {
    // Blocked storage: the default stays the first agent that can run.
  }
}

/** The agent a new draft opens on: the last one used while it can still run,
 *  otherwise the first that can; "" when none can. */
export function defaultDraftAgent(agents: AgentProviderInfo[]): string {
  let last: string | null = null;
  try {
    last = localStorage.getItem(AGENT_KEY);
  } catch {
    last = null;
  }
  const available = agents.filter((a) => a.available);
  return available.find((a) => a.agent_key === last)?.agent_key ?? available[0]?.agent_key ?? "";
}
