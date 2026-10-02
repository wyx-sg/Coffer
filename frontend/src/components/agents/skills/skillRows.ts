// src/components/agents/skills/skillRows.ts — the agent's Skills tab rows: Coffer's delivered skills and its own folders.
//
// One table lists both (spec agent-registry "Filter an agent's installed kinds
// by owner"). A Coffer row is a managed skill bound to this agent — its path is
// where the link was made. An own row is a skill folder the scan found that
// Coffer does not manage; its state says what can be done with it: adopt it,
// fix it (invalid SKILL.md), nothing (a foreign link), or remove it when Coffer
// already delivers a skill of the same name (a duplicate).
import type { StatusTone } from "@/lib/statusTone";
import type { Owner } from "@/lib/agents/owner";
import type { UnmanagedSkillOut } from "@/lib/api/agents-workspace";
import type { SkillOut } from "@/lib/api/skills";

export type OwnSkillState = "notManaged" | "foreign" | "invalid" | "duplicate" | "adoptFailed";

interface RowBase {
  key: string;
  owner: Owner;
  name: string;
  /** The line under the name. */
  description: string | null;
  /** Absolute folder path; null when Coffer has not linked it yet. */
  path: string | null;
}

interface CofferSkillRow extends RowBase {
  owner: "coffer";
  skill: SkillOut;
}

export interface OwnSkillRow extends RowBase {
  owner: "own";
  item: UnmanagedSkillOut;
  state: OwnSkillState;
  /** A second line under the state: why the last adoption failed. */
  stateNote: string | null;
}

export type SkillRow = CofferSkillRow | OwnSkillRow;

export const OWN_STATE_TONE: Record<OwnSkillState, StatusTone> = {
  notManaged: "off",
  foreign: "warn",
  invalid: "err",
  duplicate: "warn",
  adoptFailed: "err",
};

/** A failed adoption, remembered per row until the next try. */
export interface AdoptFailure {
  key: string;
  name: string;
  reason: string;
}

export function ownSkillKey(item: UnmanagedSkillOut): string {
  return `own:${item.location}:${item.name}`;
}

/** The folder's SKILL.md, the file "Open file" opens. */
export function skillFilePath(folder: string): string {
  return `${folder.replace(/[\\/]+$/, "")}/SKILL.md`;
}

interface Texts {
  foreign: string;
  duplicateOf: (name: string) => string;
}

/** Coffer's rows first, then the agent's own, each in the order it was read. */
export function buildSkillRows(
  agentUid: string,
  skills: readonly SkillOut[],
  unmanaged: readonly UnmanagedSkillOut[],
  failure: AdoptFailure | null,
  texts: Texts,
): SkillRow[] {
  const delivered: CofferSkillRow[] = [];
  for (const skill of skills) {
    const binding = skill.bindings.find((b) => b.agent_uid === agentUid);
    if (!binding) continue;
    delivered.push({
      key: `coffer:${skill.uid}`,
      owner: "coffer",
      name: skill.name,
      description: skill.description || null,
      path: binding.last_link_path,
      skill,
    });
  }
  const deliveredNames = new Set(delivered.map((row) => row.name));

  const own = unmanaged.map((item): OwnSkillRow => {
    const key = ownSkillKey(item);
    const row = ownRow(item, deliveredNames.has(item.name), texts);
    return failure?.key === key ? { ...row, state: "adoptFailed", stateNote: failure.reason } : row;
  });

  return [...delivered, ...own];
}

function ownRow(item: UnmanagedSkillOut, isDuplicate: boolean, texts: Texts): OwnSkillRow {
  const base = {
    key: ownSkillKey(item),
    owner: "own" as const,
    name: item.name,
    path: item.path,
    item,
    stateNote: null,
  };
  if (!item.valid) return { ...base, state: "invalid", description: item.reason };
  if (isDuplicate)
    return { ...base, state: "duplicate", description: texts.duplicateOf(item.name) };
  if (item.foreign_link) return { ...base, state: "foreign", description: texts.foreign };
  return { ...base, state: "notManaged", description: null };
}
