// frontend/src/components/skills/updateItems.ts
// The files of a staged update (or of a new source) as change-preview items:
// each with its operation, line counts and the diff the daemon computed.
import type { ChangeItem } from "@/lib/changePreview/changeCounts";
import type { SkillUpdatePreview } from "@/lib/api/skills";
import { CHANGE_OP, parseUnifiedDiff } from "./skillSourceHelpers";

export function updateItems(preview: SkillUpdatePreview, skillName: string): ChangeItem[] {
  return preview.changes.map((change) => ({
    id: change.path,
    agentType: "coffer",
    agentName: `Coffer · ${skillName}`,
    path: change.path,
    op: CHANGE_OP[change.status],
    added: change.additions,
    removed: change.deletions,
    diff: change.binary ? [] : parseUnifiedDiff(change.diff),
  }));
}
