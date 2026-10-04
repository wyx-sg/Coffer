// frontend/src/lib/skills/reach.ts
// The Add skill dialog's "Available to" draft: which reach the skills it adds
// get once they are added. Every agent is what an add already does.
import type { ReachMode } from "@/lib/reach/reachState";
import type { Scope } from "@/lib/api/scope";

/** @ui-only */
export interface SkillReachDraft {
  mode: ReachMode;
  scope: Scope | null;
}

export const EVERY_AGENT: SkillReachDraft = { mode: "everywhere", scope: null };
