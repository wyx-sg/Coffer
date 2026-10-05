// frontend/src/lib/skills/groups.ts — which group of the Skills library a skill sits in.
//
// Mirrors the MCP servers list: what needs the person first (Needs attention —
// a problem from lib/skills/attention.ts), then what the user runs (In use —
// switched on), then what sits idle (Off), and Coffer's own skills last (Built-in), whatever their
// reach or problems.
import type { SkillOut } from "@/lib/api/skills";

export type SkillGroup = "attention" | "inUse" | "off" | "builtin";

export const GROUP_ORDER: SkillGroup[] = ["attention", "inUse", "off", "builtin"];

export function skillGroup(
  skill: Pick<SkillOut, "builtin" | "enabled">,
  hasProblem: boolean,
): SkillGroup {
  if (skill.builtin) return "builtin";
  if (hasProblem) return "attention";
  return skill.enabled ? "inUse" : "off";
}
