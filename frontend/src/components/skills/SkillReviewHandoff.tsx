// src/components/skills/SkillReviewHandoff.tsx — hand a review of skills to an agent.
//
// The shared hand-off split button, its prompt asked of the daemon when a verb
// is picked (so it describes the folders as they are then, never a stale
// copy). Everything the agent says is a suggestion the person may decline:
// Coffer never requires a skill to change (spec skill-manager "Hand a skill's
// review to an agent").
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { skillsApi } from "@/lib/api/skills";

interface Props {
  /** The skills to review, in one prompt. */
  uids: string[];
  /** The main part's name, given the agent's name, e.g. "Check with Claude Code". */
  label: (agent: string) => string;
  /** A note for a row the button stands alone in. */
  description?: (agent: string | null) => string;
  size?: "sm" | "default";
  help?: boolean;
}

export function SkillReviewHandoff({ uids, label, description, size = "sm", help = false }: Props) {
  return (
    <AgentHandoff
      prompt={() => skillsApi.reviewHandoff(uids).then((r) => r.prompt)}
      label={label}
      description={description}
      size={size}
      help={help}
    />
  );
}
