// frontend/src/lib/skills/attention.ts
// What a skill needs the reader to know, before its description: the one line
// a library row shows in place of the description, and the banners above the
// open skill's tabs. Pure: it reads the skill, the CLIs list (for the commands
// its SKILL.md declares) and the last Check copies report.
//
// Order, most urgent first: its master folder is gone, an agent's copy is a
// folder Coffer did not put there, a command it needs is missing, its Git
// source cannot be reached, an update is waiting.
import type { Cli } from "@/lib/api/clis";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";

export type SkillAttention =
  | { kind: "masterMissing" }
  | { kind: "folderInWay"; agentName: string; entry: SkillDriftEntry }
  | { kind: "requires"; missing: string[]; loggedOut: string[]; outdated: string[] }
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
  if (skill.source_status?.error) out.push({ kind: "sourceUnreachable" });
  else if (skill.source_status?.update_available) out.push({ kind: "updateAvailable" });
  return out;
}
