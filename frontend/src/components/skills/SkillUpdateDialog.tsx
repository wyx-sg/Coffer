// src/components/skills/SkillUpdateDialog.tsx
// Review an update of a Git-imported skill: the commit range, its commits and file changes with a diff — or, over local edits, the conflict and its three choices.
//
// Spec skill-manager "Update a Git-imported skill from its source". Opening
// the dialog stages the new commit (useSkillUpdateStage); every way out that
// does not apply it — Not now, Keep my edits, closing — cancels that stage.
// Agents see an applied update at once, through their links.
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { useApplySkillUpdate, useKeepSkillEdits } from "@/lib/hooks/useSkills";
import { SkillUpdateCompare } from "./SkillUpdateCompare";
import { SkillUpdateConflict } from "./SkillUpdateConflict";
import { SkillUpdatePreviewBody } from "./SkillUpdatePreviewBody";
import { useSkillUpdateStage } from "./SkillUpdateStage";
import { repoLabel, shortCommit } from "./skillSourceHelpers";

interface Props {
  skill: SkillOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type View = "preview" | "conflict" | "compare";

export function SkillUpdateDialog({ skill, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { preview, error, discard, consumed } = useSkillUpdateStage(skill.uid, open);
  const applyUpdate = useApplySkillUpdate();
  const keepEdits = useKeepSkillEdits();
  const [view, setView] = useState<View>("preview");
  const [compareFile, setCompareFile] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<unknown>(null);
  const [confirmTake, setConfirmTake] = useState(false);

  useEffect(() => {
    setView(preview?.conflict ? "conflict" : "preview");
    setCompareFile(null);
    setApplyError(null);
  }, [preview]);

  const close = () => {
    discard();
    onOpenChange(false);
  };

  const apply = async (discardLocalEdits: boolean) => {
    if (!preview) return;
    setApplyError(null);
    try {
      await applyUpdate.mutateAsync({
        uid: skill.uid,
        stagingId: preview.staging_id,
        discardLocalEdits,
      });
    } catch (reason) {
      // Edited between the preview and the apply: offer the choice instead.
      if (reason instanceof ApiError && reason.code === "SKILL_UPDATE_CONFLICT") {
        setView("conflict");
      } else setApplyError(reason);
      throw reason;
    }
    consumed();
    onOpenChange(false);
  };

  const keep = async () => {
    if (!preview) return;
    await keepEdits.mutateAsync({ uid: skill.uid, commit: preview.to_commit });
    close();
  };

  const source = skill.source.type === "git_import" ? skill.source : null;
  const from = shortCommit(preview?.from_commit ?? source?.commit);
  const to = shortCommit(preview?.to_commit ?? skill.source_status?.latest_commit);
  const ready = !!preview && !preview.up_to_date;

  let body: ReactNode;
  if (error) {
    body = (
      <p role="alert" className="text-sm text-danger">
        {translateApiError(t, error)}
      </p>
    );
  } else if (!preview) {
    body = (
      <div className="flex flex-col gap-2" aria-busy="true">
        <span className="text-xs text-text-muted">{t("skillSources.update.loading")}</span>
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  } else if (preview.up_to_date) {
    body = (
      <div className="flex flex-col gap-1">
        <span className="text-sm font-label text-text">{t("skillSources.update.upToDate")}</span>
        <span className="text-xs text-text-muted">
          {t("skillSources.update.upToDateBody", { name: skill.name })}
        </span>
      </div>
    );
  } else if (view === "conflict") {
    body = (
      <SkillUpdateConflict
        name={skill.name}
        preview={preview}
        keeping={keepEdits.isPending}
        onKeep={() => void keep().catch(() => undefined)}
        onTake={() => setConfirmTake(true)}
      />
    );
  } else if (view === "compare") {
    body = (
      <SkillUpdateCompare
        uid={skill.uid}
        stagingId={preview.staging_id}
        paths={[...new Set([...preview.local_changes, ...preview.changes].map((c) => c.path))]}
        selected={compareFile}
        onSelect={setCompareFile}
      />
    );
  } else {
    body = <SkillUpdatePreviewBody preview={preview} />;
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
        <DialogContent className="flex max-h-[calc(100vh-4rem)] max-w-[980px] flex-col gap-0 overflow-hidden p-0">
          <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-3 pl-5 pr-12 pt-4">
            <DialogTitle>{t("skillSources.update.title", { name: skill.name })}</DialogTitle>
            <DialogDescription className="text-xs">
              {source ? `${repoLabel(source.url)} · ` : ""}
              <span className="font-mono">{from}</span>
              {to && to !== from ? <span className="font-mono">{` → ${to}`}</span> : null}
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto border-t border-border-subtle px-5 py-4">
            {body}
            {applyError ? (
              <p role="alert" className="mt-3 text-xs text-danger">
                {translateApiError(t, applyError)}
              </p>
            ) : null}
          </div>
          <DialogFooter className="m-0 mt-0 flex-row items-center justify-start gap-2 rounded-none px-5 py-3 sm:justify-start">
            <span className="min-w-0 text-xs text-text-muted">
              {ready ? t("skillSources.update.agentsNote") : null}
            </span>
            <span className="ml-auto flex shrink-0 gap-2">
              {ready && view !== "preview" ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setView(view === "compare" ? "conflict" : "compare")}
                >
                  {view === "compare"
                    ? t("skillSources.conflict.back")
                    : t("skillSources.conflict.compare")}
                </Button>
              ) : null}
              <Button type="button" variant="outline" onClick={close}>
                {ready ? t("skillSources.update.notNow") : t("common.close")}
              </Button>
              {ready && view === "preview" ? (
                <Button
                  type="button"
                  disabled={applyUpdate.isPending}
                  onClick={() => void apply(false).catch(() => undefined)}
                >
                  {applyUpdate.isPending
                    ? t("skillSources.update.applying")
                    : t("skillSources.update.apply", { commit: to })}
                </Button>
              ) : null}
            </span>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={confirmTake}
        onOpenChange={setConfirmTake}
        title={t("skillSources.conflict.confirmTitle")}
        description={t("skillSources.conflict.confirmBody", { name: skill.name, to })}
        confirmLabel={t("skillSources.conflict.take")}
        pending={applyUpdate.isPending}
        onConfirm={() => apply(true)}
      />
    </>
  );
}
