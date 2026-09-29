// frontend/src/components/skills/SkillDetailHeader.tsx
// The top of the open skill in the Skills page's reading pane: its name (a
// skill has no title — the name is fixed and is what agents load it by), the
// reach button, Delete, the description, and one meta line — name · master
// folder · where it came from · when it last changed. Coffer's own built-in
// skill gives up Delete (the daemon rewrites it at every start, so a delete
// would be refused and would undo itself one boot later); the button stays,
// disabled, and says why.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles, Trash2 } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { BuiltinMark, CopiedMark } from "@/components/skills/SkillMarks";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillOut } from "@/lib/api/skills";
import { hasCopiedDelivery } from "@/lib/skills/delivery";
import { useRemoveSkill } from "@/lib/hooks/useSkills";
import { formatDateTime } from "@/lib/utils";

const DELETE_CLASS =
  "text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive";

/** Where the skill came from, in the meta line's words. */
function useSourceLabel(skill: SkillOut): string {
  const { t } = useTranslation();
  const src = skill.source;
  switch (src.type) {
    case "local_import":
      return t("skills.detail.source.local", { path: abbreviateHomePath(src.original_path) });
    case "archive_import":
      return t("skills.detail.source.archive", { archive: src.archive_name });
    case "git_import":
      return t("skills.detail.source.git");
    default:
      return t("skills.detail.source.builtin");
  }
}

interface Props {
  skill: SkillOut;
  /** Called once the delete has landed, to leave the address of a skill that is gone. */
  onDeleted: () => void;
}

export function SkillDetailHeader({ skill, onDeleted }: Props) {
  const { t } = useTranslation();
  const remove = useRemoveSkill();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const source = useSourceLabel(skill);

  const deleteButton = (
    <Button
      variant="outline"
      size="sm"
      className={DELETE_CLASS}
      disabled={skill.builtin}
      onClick={() => setDeleteOpen(true)}
    >
      <Trash2 aria-hidden /> {t("common.delete")}
    </Button>
  );

  return (
    <header className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="inline-flex size-[30px] shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <Sparkles className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <h2 className="min-w-0 truncate text-lg font-bold">{skill.name}</h2>
        {skill.builtin ? <BuiltinMark /> : null}
        {hasCopiedDelivery(skill) ? <CopiedMark /> : null}
        <span className="ml-auto inline-flex items-center gap-2">
          <ScopeControl kind="skill" uid={skill.uid} enabled={skill.enabled} scope={skill.scope} />
          {skill.builtin ? (
            <Tooltip>
              {/* A disabled button fires no pointer events, so the wrapper is
                  what can still explain the refusal. */}
              <TooltipTrigger asChild>
                <span tabIndex={0} className="inline-flex">
                  {deleteButton}
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">{t("skills.builtinDeleteHint")}</TooltipContent>
            </Tooltip>
          ) : (
            deleteButton
          )}
        </span>
      </div>
      {skill.description ? (
        <p className="max-w-measure text-sm leading-normal text-text-muted">{skill.description}</p>
      ) : null}
      <p className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
        <span className="font-mono">{skill.name}</span>
        <span aria-hidden className="text-text-subtle">
          ·
        </span>
        <span className="font-mono" data-testid="skill-master-path">
          {abbreviateHomePath(skill.master_path)}
        </span>
        <span aria-hidden className="text-text-subtle">
          ·
        </span>
        <span data-testid="skill-detail-source">{source}</span>
        <span aria-hidden className="text-text-subtle">
          ·
        </span>
        <span>{t("skills.detail.updated", { when: formatDateTime(skill.updated_at) })}</span>
      </p>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("skills.removeConfirmTitle", { name: skill.name })}
        description={t("skills.removeConfirmBody")}
        confirmLabel={remove.isPending ? t("common.deleting") : t("common.delete")}
        pending={remove.isPending}
        onConfirm={() =>
          // Close only on success; the hook toasts a failure.
          remove.mutate(skill.uid, {
            onSuccess: () => {
              setDeleteOpen(false);
              onDeleted();
            },
          })
        }
      />
    </header>
  );
}
