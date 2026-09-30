// frontend/src/components/skills/SkillMissingMaster.tsx
// The Files tab of a skill whose master folder is gone (canvas 4.3.27): the
// two ways forward, chosen and then confirmed — Restore it from History, or
// Remove the skill (its row and settings; the confirmation is the usual
// delete). The skill's versions are not recorded yet, so Restore is shown
// but can't be chosen until the vault keeps a skill's history. The drift
// finding's hand-off asks an agent to look for a copy that can be put back.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw, Trash2 } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { SkillChoiceCards } from "@/components/skills/SkillChoiceCards";
import { SkillDeleteDialog } from "@/components/skills/SkillDeleteDialog";
import { Button } from "@/components/ui/button";
import type { SkillOut } from "@/lib/api/skills";
import { useSkillCopies } from "@/lib/hooks/useSkills";

type Way = "restore" | "remove";

interface Props {
  skill: SkillOut;
  onDeleted: () => void;
}

export function SkillMissingMaster({ skill, onDeleted }: Props) {
  const { t } = useTranslation();
  const [way, setWay] = useState<Way | null>(null);
  const [deleting, setDeleting] = useState(false);
  const handoff = useSkillCopies().data?.entries.find(
    (e) => e.kind === "missing_master" && e.skill_name === skill.name,
  )?.handoff;

  return (
    <section className="flex flex-col gap-3" aria-label={t("skills.missing.label")}>
      <SkillChoiceCards<Way>
        label={t("skills.missing.label")}
        value={way}
        onChange={setWay}
        choices={[
          {
            value: "restore",
            title: t("skills.missing.restore"),
            help: t("skills.missing.restoreUnavailable"),
            disabled: true,
          },
          {
            value: "remove",
            title: t("skills.missing.remove"),
            help: t("skills.missing.removeHelp", { name: skill.name }),
            disabled: skill.builtin,
          },
        ]}
      />
      {handoff ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="text-xs text-text-muted">{t("skills.missing.askAgent")}</span>
          <AgentHandoff prompt={handoff.prompt} size="sm" />
        </div>
      ) : null}
      <div className="flex justify-end">
        {way === "remove" ? (
          <Button variant="destructive" onClick={() => setDeleting(true)}>
            <Trash2 aria-hidden /> {t("skills.missing.removeConfirm", { name: skill.name })}
          </Button>
        ) : (
          <Button disabled>
            <RotateCcw aria-hidden /> {t("skills.missing.restoreConfirm", { name: skill.name })}
          </Button>
        )}
      </div>
      <SkillDeleteDialog
        skill={skill}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={onDeleted}
      />
    </section>
  );
}
