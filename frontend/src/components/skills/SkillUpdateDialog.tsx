// src/components/skills/SkillUpdateDialog.tsx
// Review an update of a Git-imported skill (canvas 4.3.18, 4.3.22; Foundations
// 0.7.03): the 1060 change preview — what will happen (Coffer moves the skill to
// the new commit; every agent sees the files at once through its link), the
// changed files and their diffs — with "Update to f9e8d7c" in the footer. Over
// local edits the same update is the two-way choice instead (SkillUpdateConflict).
//
// Spec skill-manager "Update a Git-imported skill from its source". Opening
// the dialog stages the new commit (useSkillUpdateStage); every way out that
// does not apply it — Cancel, Keep my edits, closing — cancels that stage.
// Agents see an applied update at once, through their links.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { useApplySkillUpdate, useKeepSkillEdits } from "@/lib/hooks/useSkills";
import { folderLabel } from "@/lib/skills/format";
import { SkillChangeDialog } from "./SkillChangeDialog";
import { SkillUpdateConflict } from "./SkillUpdateConflict";
import { useHolderSummaries } from "./skillSummaries";
import { useSkillUpdateStage } from "./SkillUpdateStage";
import { repoLabel, shortCommit } from "./skillSourceHelpers";
import { updateItems } from "./updateItems";

interface Props {
  skill: SkillOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SkillUpdateDialog({ skill, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { preview, error, discard, consumed } = useSkillUpdateStage(skill.uid, open);
  const applyUpdate = useApplySkillUpdate();
  const keepEdits = useKeepSkillEdits();
  const [applyError, setApplyError] = useState<unknown>(null);

  const source = skill.source.type === "git_import" ? skill.source : null;
  const from = shortCommit(preview?.from_commit ?? source?.commit);
  const to = shortCommit(preview?.to_commit ?? skill.source_status?.latest_commit);
  const summaries = useHolderSummaries(
    skill,
    t("skills.update.cofferMoves", {
      name: skill.name,
      from,
      to,
      count: preview?.commits.length ?? 0,
    }),
    t("skills.update.agentSees"),
  );
  const items = useMemo(
    () => (preview ? updateItems(preview, skill.name) : null),
    [preview, skill.name],
  );

  const close = () => {
    discard();
    setApplyError(null);
    onOpenChange(false);
  };

  const apply = (discardLocalEdits: boolean) => {
    if (!preview) return;
    setApplyError(null);
    applyUpdate.mutate(
      { uid: skill.uid, stagingId: preview.staging_id, discardLocalEdits },
      {
        onSuccess: () => {
          consumed();
          toast.success(t("skills.update.done", { name: skill.name, commit: to }));
          onOpenChange(false);
        },
        onError: setApplyError,
      },
    );
  };
  const keep = () => {
    if (!preview) return;
    keepEdits.mutate({ uid: skill.uid, commit: preview.to_commit }, { onSuccess: close });
  };

  const subtitle = (
    <>
      {source ? `${repoLabel(source.url)} · ` : ""}
      {source && folderLabel(source.subpath) ? `${folderLabel(source.subpath)} · ` : ""}
      <span className="font-mono">{from}</span>
      {to && to !== from ? <span className="font-mono">{` → ${to}`}</span> : null}
    </>
  );

  if (preview?.conflict && !preview.up_to_date) {
    return (
      <SkillUpdateConflict
        skill={skill}
        preview={preview}
        open={open}
        onClose={close}
        onKeep={keep}
        onTake={() => apply(true)}
        pending={keepEdits.isPending || applyUpdate.isPending}
        error={applyError}
      />
    );
  }

  let notice;
  if (error) {
    const handoff = errorHandoff(error);
    notice = (
      <div className="flex flex-col gap-2">
        <p role="alert" className="text-sm text-danger">
          {/* git's own message says what it could not reach; the generic copy would hide it. */}
          {error instanceof ApiError && error.code === "SKILL_SOURCE_UNREACHABLE"
            ? error.envelopeMessage
            : translateApiError(t, error)}
        </p>
        {handoff ? <AgentHandoff prompt={handoff} size="sm" /> : null}
      </div>
    );
  } else if (preview?.up_to_date) {
    notice = (
      <div className="flex flex-col gap-1">
        <span className="text-sm font-label text-text">{t("skillSources.update.upToDate")}</span>
        <span className="text-xs text-text-muted">
          {t("skillSources.update.upToDateBody", { name: skill.name })}
        </span>
      </div>
    );
  }

  return (
    <SkillChangeDialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title={t("skillSources.update.title", { name: skill.name })}
      subtitle={subtitle}
      items={items}
      summaries={summaries}
      notice={notice}
      loadingLabel={t("skillSources.update.loading")}
      note={t("skills.update.note", { name: skill.name })}
      confirmLabel={t("skillSources.update.apply", { commit: to })}
      onConfirm={() => apply(false)}
      pending={applyUpdate.isPending}
      closeOnly={Boolean(error || preview?.up_to_date)}
      error={
        applyError ? (
          <DialogErrorBanner
            title={t("skills.update.failed")}
            message={translateApiError(t, applyError)}
          />
        ) : null
      }
    />
  );
}
