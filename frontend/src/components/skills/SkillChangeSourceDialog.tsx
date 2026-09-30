// frontend/src/components/skills/SkillChangeSourceDialog.tsx
// "Change source of terraform-plan" (canvas 4.3.43; spec skill-manager "Change
// a Git-imported skill's source"): the repository URL, branch or tag and
// folder of the new source, prefilled with the current one. Check source
// clones it and shows the change against the current version — nothing is
// replaced until the reader takes it; Cancel, or closing, drops the stage.
// The name stays the skill's.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { SkillAddGitFields, type GitLocation } from "@/components/skills/SkillAddSourceFields";
import { SkillUpdatePreviewBody } from "@/components/skills/SkillUpdatePreviewBody";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { SkillOut, SkillUpdatePreview } from "@/lib/api/skills";
import { useChangeSkillSource } from "@/lib/hooks/useSkillCopies";
import { useApplySkillUpdate, useCancelSkillStage } from "@/lib/hooks/useSkills";
import { folderLabel } from "@/lib/skills/format";
import { cn } from "@/lib/utils";
import { repoLabel, shortCommit } from "./skillSourceHelpers";

interface Props {
  skill: SkillOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SkillChangeSourceDialog({ skill, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const change = useChangeSkillSource();
  const apply = useApplySkillUpdate();
  const cancelStage = useCancelSkillStage();
  const source = skill.source.type === "git_import" ? skill.source : null;
  const [loc, setLoc] = useState<GitLocation>({ url: "", ref: "", path: "" });
  const [preview, setPreview] = useState<SkillUpdatePreview | null>(null);
  const staged = useRef<string | null>(null);

  useEffect(() => {
    if (!open || !source) return;
    setLoc({ url: source.url, ref: source.ref ?? "", path: source.subpath });
    setPreview(null);
    change.reset();
    apply.reset();
    // Seed once per opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!source) return null;

  const close = () => {
    if (staged.current) cancelStage.mutate(staged.current);
    staged.current = null;
    onOpenChange(false);
  };
  const check = () =>
    change.mutate(
      {
        uid: skill.uid,
        url: loc.url.trim(),
        ref: loc.ref.trim() || null,
        path: loc.path.trim() || null,
      },
      {
        onSuccess: (p) => {
          staged.current = p.staging_id;
          setPreview(p);
        },
      },
    );
  const take = () =>
    preview &&
    apply.mutate(
      { uid: skill.uid, stagingId: preview.staging_id, discardLocalEdits: true },
      {
        onSuccess: () => {
          staged.current = null;
          onOpenChange(false);
        },
      },
    );
  const error = change.error;
  const unreachable = error instanceof ApiError && error.code === "SKILL_SOURCE_UNREACHABLE";
  const handoff = errorHandoff(error);
  const now = [repoLabel(source.url), folderLabel(source.subpath), t("skills.detail.pinned")]
    .filter(Boolean)
    .join(" · ");

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent
        className={cn(
          "flex max-h-[calc(100vh-4rem)] flex-col gap-0 overflow-hidden p-0",
          preview ? "max-w-[980px]" : "max-w-[540px]",
        )}
      >
        <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-3 pl-5 pr-12 pt-4">
          <DialogTitle>{t("skills.changeSource.title", { name: skill.name })}</DialogTitle>
          <DialogDescription className="text-xs">
            {t("skills.changeSource.now")} {now}{" "}
            <span className="font-mono">{shortCommit(source.commit)}</span>
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
          {preview ? (
            <SkillUpdatePreviewBody preview={preview} skill={skill} />
          ) : (
            <>
              <SkillAddGitFields
                value={loc}
                onChange={setLoc}
                disabled={change.isPending}
                urlHelp={false}
                urlError={unreachable ? error.envelopeMessage : null}
              />
              {error && !unreachable ? (
                <p role="alert" className="text-xs text-danger">
                  {translateApiError(t, error)}
                </p>
              ) : null}
              {handoff ? <AgentHandoff prompt={handoff} size="sm" /> : null}
              <Alert variant="info">
                <Info aria-hidden />
                <AlertTitle>{t("skills.changeSource.noteTitle")}</AlertTitle>
                <AlertDescription>
                  {t("skills.changeSource.noteBody", { name: skill.name })}
                </AlertDescription>
              </Alert>
            </>
          )}
          {apply.error ? (
            <p role="alert" className="text-xs text-danger">
              {translateApiError(t, apply.error)}
            </p>
          ) : null}
        </div>
        <DialogFooter className="m-0 mt-0 flex-row items-center justify-end gap-2 rounded-none px-5 py-3">
          <Button variant="outline" onClick={close}>
            {t("common.cancel")}
          </Button>
          {preview ? (
            <Button disabled={apply.isPending} onClick={take}>
              {t("skills.changeSource.take", { commit: shortCommit(preview.to_commit) })}
            </Button>
          ) : (
            <Button disabled={!loc.url.trim() || change.isPending} onClick={check}>
              {change.isPending
                ? t("skills.changeSource.checking")
                : t("skills.changeSource.check")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
