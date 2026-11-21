// frontend/src/lib/skills/sharedReaders.ts — which agents see a skill delivered for another.
//
// A skill reaches an agent as a link in the folder the agent reads, and some
// folders are read by several agents (ADR
// a-shared-skills-directory-holds-one-link-for-every-reader): Codex, Cursor,
// OpenCode and DeepSeek Harness all read ~/.agents/skills, and Cursor and
// OpenCode also read Claude Code's ~/.claude/skills. So a scope that names one
// of them cannot keep the skill from the others. The skill reach panel says so
// in one line instead of offering a choice it cannot honour. Everything here
// comes from each type's `skill_dirs_read` (the folder Coffer delivers to,
// first, then the ones it also reads), never from an agent's name.
import { useTranslation } from "react-i18next";

import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgentTypes } from "@/lib/hooks/useAgents";

/** One folder more than one added agent reads. */
export interface SharedFolder {
  /** The agents Coffer delivers to this folder. */
  delivered: string[];
  /** The added agents that also read it on their own. */
  alsoReading: string[];
}

/** The skills folders more than one added agent reads, in the types' order. */
export function sharedFolders(types: readonly AgentTypeOut[]): SharedFolder[] {
  const added = types.filter((t) => t.uid !== null);
  const folders = [...new Set(added.map((t) => t.skill_dirs_read[0]).filter(Boolean))];
  return folders.flatMap((dir) => {
    const delivered = added.filter((t) => t.skill_dirs_read[0] === dir);
    const alsoReading = added.filter(
      (t) => t.skill_dirs_read[0] !== dir && t.skill_dirs_read.includes(dir),
    );
    if (delivered.length + alsoReading.length < 2) return [];
    return [
      {
        delivered: delivered.map((t) => t.display_name),
        alsoReading: alsoReading.map((t) => t.display_name),
      },
    ];
  });
}

/** The line the skill reach panel shows under its agent list, or undefined. */
export function useSharedReadersNote(): string | undefined {
  const { t, i18n } = useTranslation();
  const { data } = useAgentTypes();
  const list = new Intl.ListFormat(i18n.language, { type: "conjunction" });
  const lines = sharedFolders(data ?? []).map((f) =>
    f.delivered.length > 1
      ? f.alsoReading.length
        ? t("skills.reach.sharedFolderAlso", {
            agents: list.format(f.delivered),
            also: list.format(f.alsoReading),
          })
        : t("skills.reach.sharedFolder", { agents: list.format(f.delivered) })
      : t("skills.reach.alsoSeen", { agent: f.delivered[0], others: list.format(f.alsoReading) }),
  );
  return lines.length ? lines.join(" ") : undefined;
}
