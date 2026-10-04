// frontend/src/lib/skills/groups.ts — which group of the Skills library a skill sits in.
//
// Mirrors the MCP servers list: what needs the person first (Needs attention —
// a problem from lib/skills/attention.ts), then what the user runs (In use —
// reaches at least one agent), then what sits idle (Off — switched off, or
// limited to nobody), and Coffer's own skills last (Built-in), whatever their
// reach or problems.
import type { SkillOut } from "@/lib/api/skills";

export type SkillGroup = "attention" | "inUse" | "off" | "builtin";

export const GROUP_ORDER: SkillGroup[] = ["attention", "inUse", "off", "builtin"];

export function skillGroup(
  skill: Pick<SkillOut, "builtin" | "enabled" | "scope">,
  hasProblem: boolean,
): SkillGroup {
  if (skill.builtin) return "builtin";
  if (hasProblem) return "attention";
  const agents = skill.scope?.agents ?? null;
  return skill.enabled && (agents === null || agents.length > 0) ? "inUse" : "off";
}
