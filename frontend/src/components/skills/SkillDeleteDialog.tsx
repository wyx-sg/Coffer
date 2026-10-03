// frontend/src/components/skills/SkillDeleteDialog.tsx
// "Delete pdf?" (canvas 4.3.11, 420 wide): deletes the master folder and every
// agent's link, naming the agents that have it, and says History keeps the
// files. A refusal stays in the dialog (4.3.55): when an agent's copy is no
// longer Coffer's link the daemon refuses the whole delete (409
// SKILL_COPY_NOT_OURS, nothing changed) and the dialog says which folder and
// that Coffer only removes what it made; the primary button then reads "Delete,
// keep <Agent>'s folder" and sends the delete again leaving that folder alone.
// Any other failure is the usual inline error with Try again. Success is a
// toast; the dialog closes only once the delete lands.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useRemoveSkill } from "@/lib/hooks/useSkills";
import { joinNames } from "@/lib/skills/names";
import { notOursOf } from "@/lib/skills/notOurs";
import { NotOursNotice } from "@/components/skills/SkillNotOursNotice";

interface Props {
  skill: SkillOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}

export function SkillDeleteDialog({ skill, open, onOpenChange, onDeleted }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const remove = useRemoveSkill();
  const { data: agents = [] } = useAgents();
  const label = (name: string) => agents.find((a) => a.name === name)?.display_name ?? name;
  const holders = skill.bindings.map(
    (b) => agents.find((a) => a.uid === b.agent_uid)?.display_name ?? b.agent_name,
  );
  const refused = notOursOf(remove.error);
  const description =
    holders.length === 0
      ? t("skills.delete.bodyNone")
      : t("skills.delete.body", {
          count: holders.length,
          agents: joinNames(holders, i18n.language),
        });

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) remove.reset();
        onOpenChange(next);
      }}
      title={t("skills.delete.title", { name: skill.name })}
      description={description}
      confirmLabel={
        refused
          ? t("skills.delete.keepFolder", { agent: label(refused.agentName) })
          : t("skills.delete.confirm")
      }
      pendingLabel={t("common.deleting")}
      errorTitle={t("common.couldntDelete", { name: skill.name })}
      pending={remove.isPending}
      error={remove.error && !refused ? remove.error : undefined}
      onConfirm={() =>
        remove.mutate(
          { uid: skill.uid, keepForeignCopies: refused !== null },
          {
            onSuccess: () => {
              toast.success(t("skills.delete.done", { name: skill.name }));
              onOpenChange(false);
              onDeleted();
            },
          },
        )
      }
    >
      <p className="text-xs text-text-muted">{t("skills.delete.noUndo")}</p>
      {refused ? (
        <NotOursNotice
          title={t("skills.delete.refusedTitle")}
          path={refused.path}
          tail={t("skills.delete.refusedBody", { agent: label(refused.agentName) })}
        />
      ) : null}
    </ConfirmDialog>
  );
}
