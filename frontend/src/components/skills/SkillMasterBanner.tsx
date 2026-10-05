// frontend/src/components/skills/SkillMasterBanner.tsx
// The banner of a skill whose master folder is gone (canvas 4.3.04): it names
// the folder, says its reach is still here, and carries the two ways forward —
// the hand-off that has an agent look for a copy to put back (Copy prompt, Ask
// an agent; spec skill-manager "Hand unsettled skill drift to an agent with a
// prompt") and Delete skill… (the usual confirmation). The prompt is the one the
// drift report carries for this skill's missing master, asked for when the
// person picks a verb; the choice stays the person's.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { SkillBannerFrame } from "@/components/skills/SkillBannerFrame";
import { SkillDeleteDialog } from "@/components/skills/SkillDeleteDialog";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import { skillsApi, type SkillOut } from "@/lib/api/skills";

interface Props {
  skill: SkillOut;
  onDeleted: () => void;
}

/** The hand-off the drift report carries for this skill's missing master. */
async function missingMasterPrompt(skillName: string): Promise<string> {
  const report = await skillsApi.verify();
  const entry = report.entries.find(
    (e) => e.skill_name === skillName && e.kind === "missing_master",
  );
  if (!entry?.handoff) throw new Error("no hand-off for this skill");
  return entry.handoff.prompt;
}

export function SkillMasterBanner({ skill, onDeleted }: Props) {
  const { t } = useTranslation();
  const [deleting, setDeleting] = useState(false);

  return (
    <>
      <SkillBannerFrame
        tone="error"
        testId="skill-banner-master"
        title={t("skills.banner.masterTitle")}
        actions={
          <>
            <AgentHandoff size="sm" prompt={() => missingMasterPrompt(skill.name)} />
            <Button
              variant="outline"
              size="sm"
              disabled={skill.builtin}
              onClick={() => setDeleting(true)}
            >
              {t("skills.missing.deleteButton")}
            </Button>
          </>
        }
      >
        {t("skills.banner.masterBody", { path: abbreviateHomePath(skill.master_path) })}
      </SkillBannerFrame>
      <SkillDeleteDialog
        skill={skill}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={onDeleted}
      />
    </>
  );
}
