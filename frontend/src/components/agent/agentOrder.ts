// src/components/agent/agentOrder.ts — the one order agents appear in: Claude Code, then Codex, as on the Agents page.
//
// A position means the same agent everywhere (badges, checklists, tables), so
// every list of agents sorts through here: known types first in a fixed order,
// anything else after, then by name.

const TYPE_ORDER = ["claude_code", "codex"];

function typeRank(type: string): number {
  const i = TYPE_ORDER.indexOf(type);
  return i === -1 ? TYPE_ORDER.length : i;
}

/** A sorted copy of `agents` in Agents-page order. */
export function sortAgents<T extends { type: string; name?: string }>(agents: readonly T[]): T[] {
  return [...agents].sort(
    (a, b) => typeRank(a.type) - typeRank(b.type) || (a.name ?? "").localeCompare(b.name ?? ""),
  );
}
