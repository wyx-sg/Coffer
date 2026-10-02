// frontend/src/lib/skills/groups.ts — which group of the Skills library a skill sits in.
//
// Mirrors the MCP servers list: what the user runs first (In use — reaches at
// least one agent), then what sits idle (Unused — switched off, or limited to
// nobody), and Coffer's own skills last (Built-in), whatever their reach.
import type { SkillOut } from "@/lib/api/skills";

export type SkillGroup = "inUse" | "unused" | "builtin";

export const GROUP_ORDER: SkillGroup[] = ["inUse", "unused", "builtin"];

export function skillGroup(skill: Pick<SkillOut, "builtin" | "enabled" | "scope">): SkillGroup {
  if (skill.builtin) return "builtin";
  const agents = skill.scope?.agents ?? null;
  return skill.enabled && (agents === null || agents.length > 0) ? "inUse" : "unused";
}
