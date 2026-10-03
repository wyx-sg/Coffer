// src/components/agents/skills/skillRows.ts — the agent's Skills tab: what Coffer delivers, and the agent's own folders.
//
// Coffer's skills are not rows (spec agent-registry "Show what Coffer manages
// for an agent in one row"): the tab names them in one "From Coffer" row. An
// own row is a skill folder the scan found that Coffer does not manage; its
// state says what can be done with it: adopt it, nothing (invalid SKILL.md, a
// foreign link), or delete it when Coffer already delivers a skill of the same
// name (a duplicate). Rows are ordered invalid, foreign, duplicate, unmanaged.
import type { StatusTone } from "@/lib/statusTone";
import type { UnmanagedSkillOut } from "@/lib/api/agents-workspace";
import type { SkillOut } from "@/lib/api/skills";

export type OwnSkillState = "invalid" | "foreign" | "duplicate" | "unmanaged";

export interface OwnSkillRow {
  key: string;
  name: string;
  item: UnmanagedSkillOut;
  state: OwnSkillState;
  /** The Coffer skill of the same name, when this is a duplicate. */
  duplicateOf: string | null;
}

export const OWN_STATE_TONE: Record<OwnSkillState, StatusTone> = {
  invalid: "err",
  foreign: "warn",
  duplicate: "warn",
  unmanaged: "off",
};

const ORDER: Record<OwnSkillState, number> = { invalid: 0, foreign: 1, duplicate: 2, unmanaged: 3 };

export function ownSkillKey(item: UnmanagedSkillOut): string {
  return `own:${item.location}:${item.name}`;
}

/** The folder a skill sits in (its parent), the row's "where". */
export function skillParentDir(folder: string): string {
  return folder.replace(/[\\/]+$/, "").replace(/[\\/][^\\/]*$/, "");
}

/** The names of the skills Coffer delivers into this agent, in the library's order. */
export function cofferSkillNames(agentUid: string, skills: readonly SkillOut[]): string[] {
  return skills
    .filter((skill) => skill.bindings.some((b) => b.agent_uid === agentUid))
    .map((skill) => skill.name);
}

/** The agent's own folders, worst first; each group keeps the order it was read. */
export function buildOwnSkillRows(
  unmanaged: readonly UnmanagedSkillOut[],
  deliveredNames: readonly string[],
): OwnSkillRow[] {
  const delivered = new Set(deliveredNames);
  const rows = unmanaged.map((item): OwnSkillRow => {
    const state: OwnSkillState = !item.valid
      ? item.foreign_link
        ? "foreign"
        : "invalid"
      : delivered.has(item.name)
        ? "duplicate"
        : item.foreign_link
          ? "foreign"
          : "unmanaged";
    return {
      key: ownSkillKey(item),
      name: item.name,
      item,
      state,
      duplicateOf: state === "duplicate" ? item.name : null,
    };
  });
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => ORDER[a.row.state] - ORDER[b.row.state] || a.index - b.index)
    .map(({ row }) => row);
}
