// frontend/src/lib/skills/tree.ts
// The order the Files tab lists a skill folder in: SKILL.md first, then
// folders, then files, each group by name — without Coffer's own bookkeeping
// file, which is not part of the skill.
import type { SkillFileNode } from "@/lib/api/skills";

/** Coffer's own bookkeeping file in a master folder, not part of the skill. */
const META_FILE = ".coffer.meta.json";

export function sortSkillNodes(nodes: readonly SkillFileNode[]): SkillFileNode[] {
  const rank = (n: SkillFileNode) => (n.name === "SKILL.md" ? 0 : n.type === "dir" ? 1 : 2);
  return nodes
    .filter((n) => n.name !== META_FILE)
    .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}
