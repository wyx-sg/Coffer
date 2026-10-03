// frontend/src/components/skills/SkillDeleteDialog.tsx
// "Delete pdf?" (canvas 4.3.06): deletes the master folder and every agent's
// link, naming the agents that have it. A refusal stays in the dialog: when an
// agent's copy is no longer Coffer's link the daemon refuses the whole delete
// (409 SKILL_COPY_NOT_OURS, nothing changed) and the dialog says which folder
// and what to do, with Try again. The dialog closes only once the delete lands.
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath } from "@/lib/agents/display";
import { ApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useRemoveSkill } from "@/lib/hooks/useSkills";
import { joinNames } from "@/lib/skills/names";

interface Props {
  skill: SkillOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}

/** The folder a refused delete names, from the refusal's details. */
function refusedPath(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.code !== "SKILL_COPY_NOT_OURS") return null;
  const details = error.details as { path?: unknown } | undefined;
  return typeof details?.path === "string" ? details.path : "";
}

export function SkillDeleteDialog({ skill, open, onOpenChange, onDeleted }: Props) {
  const { t, i18n } = useTranslation();
  const remove = useRemoveSkill();
  const { data: agents = [] } = useAgents();
  const holders = skill.bindings.map(
    (b) => agents.find((a) => a.uid === b.agent_uid)?.display_name ?? b.agent_name,
  );
  const refused = refusedPath(remove.error);
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
      confirmLabel={remove.error ? t("common.tryAgain") : t("skills.delete.confirm")}
      pendingLabel={t("common.deleting")}
      errorTitle={t("common.couldntDelete", { name: skill.name })}
      pending={remove.isPending}
      error={remove.error && refused === null ? remove.error : undefined}
      onConfirm={() =>
        remove.mutate(skill.uid, {
          onSuccess: () => {
            onOpenChange(false);
            onDeleted();
          },
        })
      }
    >
      <p className="text-xs text-text-muted">{t("skills.delete.noUndo")}</p>
      {refused !== null ? (
        <div role="alert" className="flex gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-xs">
          <AlertCircle className="mt-0.5 size-[15px] shrink-0 text-danger" aria-hidden />
          <div className="flex flex-col gap-0.5">
            <p className="text-sm font-label text-text">
              {t("skills.delete.failedTitle", { name: skill.name })}
            </p>
            <p className="text-text-muted">
              <code className="font-mono text-text">{abbreviateHomePath(refused)}</code>{" "}
              {t("skills.delete.notOurs")}
            </p>
          </div>
        </div>
      ) : null}
    </ConfirmDialog>
  );
}
