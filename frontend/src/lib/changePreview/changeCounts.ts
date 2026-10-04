// frontend/src/lib/changePreview/changeCounts.ts
// Pure helpers for the change preview: the shared types, counts by operation, grouping by agent, progress.

export type ChangeOp = "add" | "modify" | "remove";
export type ChangeStatus = "pending" | "applying" | "applied" | "failed";

export interface DiffLine {
  kind: "context" | "add" | "remove" | "hunk";
  text: string;
  oldNo?: number;
  newNo?: number;
}

export interface ChangeItem {
  id: string;
  agentType: string;
  agentName?: string;
  path: string;
  op: ChangeOp;
  added?: number;
  removed?: number;
  diff?: DiffLine[];
  status?: ChangeStatus;
  error?: string;
}

export interface ChangeSummaryLine {
  agentType: string;
  agentName?: string;
  text: string;
}

export type ChangePreviewState =
  | "computing"
  | "empty"
  | "ready"
  | "applying"
  | "applied"
  | "failed";

/** The order op counts are listed in: Modify, Add, Remove. */
export const OP_ORDER: readonly ChangeOp[] = ["modify", "add", "remove"];

export interface AgentGroup {
  key: string;
  agentType: string;
  agentName?: string;
  items: ChangeItem[];
}

/** An agent is its type plus its name, so two agents of one type stay apart. */
function agentKey(agentType: string, agentName?: string): string {
  return `${agentType}\u0000${agentName ?? ""}`;
}

/** Groups items by agent, in the order each agent first appears; items keep their order. */
export function groupByAgent(items: readonly ChangeItem[]): AgentGroup[] {
  const groups = new Map<string, AgentGroup>();
  for (const item of items) {
    const key = agentKey(item.agentType, item.agentName);
    let group = groups.get(key);
    if (!group) {
      group = { key, agentType: item.agentType, agentName: item.agentName, items: [] };
      groups.set(key, group);
    }
    group.items.push(item);
  }
  return [...groups.values()];
}

export function failedIds(items: readonly ChangeItem[]): string[] {
  return items.filter((item) => item.status === "failed").map((item) => item.id);
}

/** Position of the write in flight: applied ones plus the one being written (at least 1, at most total). */
export function applyingPosition(items: readonly ChangeItem[]): number {
  const applied = items.filter((item) => item.status === "applied").length;
  const inFlight = items.some((item) => item.status === "applying") ? 1 : 0;
  return Math.min(items.length, Math.max(1, applied + inFlight));
}

/** Folders on the board are the entries without an extension (a skill directory, say). */
export function looksLikeFolder(path: string): boolean {
  if (path.endsWith("/")) return true;
  const last = path.split("/").pop() ?? "";
  return !last.includes(".");
}
