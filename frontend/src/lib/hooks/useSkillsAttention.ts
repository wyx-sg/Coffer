// src/lib/hooks/useSkillsAttention.ts — how many things on the Skills page need the person: the sidebar badge's count.
//
// Skills needing attention (a master folder gone, a folder in the way of an
// agent's link, a command, tool or secret it needs that is not ready, a Git
// source that cannot be reached — lib/skills/attention.ts, the same set the
// library's "Needs attention" group lists) plus the folders in the skills store
// that no skill claims (the "Not in your library" rows). The copies findings are
// the last Check copies report this session has — nothing is checked for the
// badge. `null` while the skills list has not answered, so the sidebar shows no
// badge rather than a wrong one.
import { useClis } from "@/lib/hooks/useClis";
import { useSkillOrphans } from "@/lib/hooks/useSkillCopies";
import { useSkillCopies, useSkills } from "@/lib/hooks/useSkills";
import { skillsNeedingAttention } from "@/lib/skills/attention";

export function useSkillsAttentionCount(): number | null {
  const skills = useSkills().data;
  const clis = useClis().data?.items ?? [];
  const entries = useSkillCopies().data?.entries;
  const orphans = useSkillOrphans().data;
  if (!skills) return null;
  return skillsNeedingAttention(skills, clis, entries).length + (orphans?.length ?? 0);
}
