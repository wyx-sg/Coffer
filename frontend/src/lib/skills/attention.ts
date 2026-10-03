// frontend/src/lib/skills/attention.ts
// What a skill needs the reader to know, before its description: the one line
// a library row shows in place of the description, and the banners above the
// open skill's tabs. Pure: it reads the skill, the CLIs list (for the commands
// its SKILL.md declares) and the last Check copies report.
//
// Order, most urgent first: its master folder is gone, an agent's copy is a
// folder Coffer did not put there, a command it needs is missing, a tool it
// calls (an MCP server or a custom-tool group) is off or failing, a secret it
// needs is not set (the skill read model answers that from Coffer's secret
// store, by name only), its Git source cannot be reached, an update is waiting.
//
// Everything except the waiting update is a PROBLEM: it files the skill under
// "Needs attention" in the library, tints the header pill and counts toward
// the sidebar badge (`skillsNeedingAttention` is the one count both read).
import type { Cli } from "@/lib/api/clis";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";

/** A tool the skill calls that is not healthy: its name, why, and where it lives. */
export type SkillToolState = SkillOut["requires_tools"][number];

export type SkillAttention =
  | { kind: "masterMissing" }
  | { kind: "folderInWay"; agentName: string; entry: SkillDriftEntry }
  | { kind: "requires"; missing: string[]; loggedOut: string[]; outdated: string[] }
  | { kind: "toolOff"; tools: SkillToolState[] }
  | { kind: "secrets"; missing: string[] }
  | { kind: "sourceUnreachable" }
  | { kind: "updateAvailable" };

/** The drift findings that are about this skill, keyed by what they say. */
function findingsFor(
  skill: Pick<SkillOut, "name">,
  entries: readonly SkillDriftEntry[] | undefined,
): SkillDriftEntry[] {
  return (entries ?? []).filter((e) => e.skill_name === skill.name);
}

/** The declared commands that are not ready on this machine, by state. */
function requireProblems(skill: Pick<SkillOut, "requires">, clis: readonly Cli[]) {
  const byCommand = new Map(clis.map((c) => [c.command, c]));
  const missing: string[] = [];
  const loggedOut: string[] = [];
  const outdated: string[] = [];
  for (const req of skill.requires) {
    const cli = byCommand.get(req.command);
    if (cli?.status === "missing") missing.push(req.command);
    else if (cli?.status === "logged_out") loggedOut.push(req.command);
    else if (cli?.status === "outdated") outdated.push(req.command);
  }
  return { missing, loggedOut, outdated };
}

/** Every attention item for the skill, most urgent first. */
export function skillAttention(
  skill: SkillOut,
  clis: readonly Cli[],
  entries: readonly SkillDriftEntry[] | undefined,
): SkillAttention[] {
  const out: SkillAttention[] = [];
  const findings = findingsFor(skill, entries);
  if (skill.master_missing || findings.some((e) => e.kind === "missing_master")) {
    out.push({ kind: "masterMissing" });
  }
  for (const e of findings) {
    if (e.kind === "replaced_with_regular") {
      out.push({ kind: "folderInWay", agentName: e.agent_name, entry: e });
    }
  }
  const problems = requireProblems(skill, clis);
  if (problems.missing.length + problems.loggedOut.length + problems.outdated.length > 0) {
    out.push({ kind: "requires", ...problems });
  }
  const sick = (skill.requires_tools ?? []).filter((tool) => tool.status !== "healthy");
  if (sick.length > 0) out.push({ kind: "toolOff", tools: sick });
  const unset = (skill.requires_secrets ?? []).filter((s) => !s.is_set).map((s) => s.name);
  if (unset.length > 0) out.push({ kind: "secrets", missing: unset });
  if (skill.source_status?.error) out.push({ kind: "sourceUnreachable" });
  else if (skill.source_status?.update_available) out.push({ kind: "updateAvailable" });
  return out;
}

/** Whether the item is a problem to fix (everything but an update waiting). */
export function isProblem(item: SkillAttention): boolean {
  return item.kind !== "updateAvailable";
}

/** The skill's problems: what files it under "Needs attention". Built-in skills have none. */
export function skillProblems(
  skill: SkillOut,
  clis: readonly Cli[],
  entries: readonly SkillDriftEntry[] | undefined,
): SkillAttention[] {
  return skill.builtin ? [] : skillAttention(skill, clis, entries).filter(isProblem);
}

/** The skills with at least one problem — the library's "Needs attention" group
 *  and the sidebar badge count the same set. */
export function skillsNeedingAttention(
  skills: readonly SkillOut[],
  clis: readonly Cli[],
  entries: readonly SkillDriftEntry[] | undefined,
): SkillOut[] {
  return skills.filter((s) => skillProblems(s, clis, entries).length > 0);
}

/** The state pill of the open skill's header (canvas 4.3 SkillHeader). */
export type SkillStatus =
  | "inUse"
  | "off"
  | "masterMissing"
  | "folderInWay"
  | "commandMissing"
  | "commandNotReady"
  | "toolOff"
  | "secretMissing"
  | "sourceUnreachable";

export function skillStatus(skill: SkillOut, items: readonly SkillAttention[]): SkillStatus {
  const first = skill.builtin ? undefined : items.find(isProblem);
  switch (first?.kind) {
    case "masterMissing":
      return "masterMissing";
    case "folderInWay":
      return "folderInWay";
    case "requires":
      return first.missing.length > 0 ? "commandMissing" : "commandNotReady";
    case "toolOff":
      return "toolOff";
    case "secrets":
      return "secretMissing";
    case "sourceUnreachable":
      return "sourceUnreachable";
    default:
      return skill.enabled ? "inUse" : "off";
  }
}
