// frontend/src/components/skills/SkillChangeSourceDialog.tsx
// "Change source of terraform-plan" (canvas 4.3.24; spec skill-manager "Change
// a Git-imported skill's source"): the repository URL, branch or tag and folder
// of the new source, prefilled with the current one, in a 480 form. Check source
// clones it and lists the names of the files that would change against the
// current version (SkillSourceChangeReview) — nothing is replaced until the
// person takes it; Cancel, or closing, drops the stage. The name stays the
// skill's.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { SkillOut, SkillSourceChange } from "@/lib/api/skills";
import { useChangeSkillSource } from "@/lib/hooks/useSkillCopies";
import { useApplySkillSourceChange, useCancelSkillStage } from "@/lib/hooks/useSkills";
import { folderLabel } from "@/lib/skills/format";
import { SourceField as Field } from "./SkillSourceField";
import { SkillSourceChangeReview } from "./SkillSourceChangeReview";
import { repoLabel, shortCommit } from "./skillSourceHelpers";

interface Props {
  skill: SkillOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface Location {
  url: string;
  ref: string;
  path: string;
}

export function SkillChangeSourceDialog({ skill, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const change = useChangeSkillSource();
  const apply = useApplySkillSourceChange();
  const cancelStage = useCancelSkillStage();
  const source = skill.source.type === "git_import" ? skill.source : null;
  const [loc, setLoc] = useState<Location>({ url: "", ref: "", path: "" });
  const [preview, setPreview] = useState<SkillSourceChange | null>(null);
  const staged = useRef<string | null>(null);
  const to = shortCommit(preview?.commit);

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
      { uid: skill.uid, stagingId: preview.staging_id },
      {
        onSuccess: () => {
          staged.current = null;
          toast.success(
            t("skills.changeSource.done", { name: skill.name, repo: repoLabel(loc.url) }),
          );
          onOpenChange(false);
        },
      },
    );

  if (preview) {
    return (
      <SkillSourceChangeReview
        open={open}
        title={t("skills.changeSource.title", { name: skill.name })}
        subtitle={`${repoLabel(loc.url)} · ${folderLabel(loc.path) ?? t("skills.banner.repoTop")} · ${to}`}
        change={preview}
        takeLabel={t("skills.changeSource.take", { commit: to })}
        pending={apply.isPending}
        error={apply.error}
        onTake={take}
        onCancel={close}
      />
    );
  }

  const error = change.error;
  const unreachable = error instanceof ApiError && error.code === "SKILL_SOURCE_UNREACHABLE";
  const handoff = errorHandoff(error);
  const now = [
    repoLabel(source.url),
    folderLabel(source.subpath) ?? t("skills.banner.repoTop"),
    shortCommit(source.commit),
  ];

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="flex max-h-[calc(100vh-4rem)] max-w-[480px] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-0 pl-5 pr-12 pt-4">
          <DialogTitle>{t("skills.changeSource.title", { name: skill.name })}</DialogTitle>
          <DialogDescription className="text-xs">
            {t("skills.changeSource.now")}{" "}
            {now.map((part, i) => (
              <span key={i}>
                {i > 0 ? " · " : ""}
                <span className="font-mono text-2xs">{part}</span>
              </span>
            ))}
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-[18px] pt-4">
          <Field
            id="skill-source-url"
            label={t("skillSources.git.url")}
            required
            help={unreachable ? error.envelopeMessage : null}
            helpTone={unreachable ? "danger" : undefined}
            value={loc.url}
            disabled={change.isPending}
            onChange={(url) => setLoc({ ...loc, url })}
          />
          <Field
            id="skill-source-ref"
            label={t("skillSources.git.ref")}
            help={t("skills.changeSource.refHelp")}
            value={loc.ref}
            disabled={change.isPending}
            onChange={(ref) => setLoc({ ...loc, ref })}
          />
          <Field
            id="skill-source-path"
            label={t("skillSources.git.path")}
            help={t("skills.changeSource.pathHelp")}
            value={loc.path}
            disabled={change.isPending}
            onChange={(path) => setLoc({ ...loc, path })}
          />
          {error && !unreachable ? (
            <p role="alert" className="text-xs text-danger">
              {translateApiError(t, error)}
            </p>
          ) : null}
          {handoff ? <AgentHandoff prompt={handoff} size="sm" /> : null}
        </div>
        <DialogFooter className="m-0 mt-0 flex-row items-center justify-start gap-2 rounded-none px-5 py-3 sm:justify-start">
          <span className="min-w-0 text-xs text-text-muted">
            {t("skills.changeSource.noteForm")}
          </span>
          <span className="ml-auto flex shrink-0 gap-2">
            <Button variant="ghost" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button disabled={!loc.url.trim()} loading={change.isPending} onClick={check}>
              {change.isPending
                ? t("skills.changeSource.checking")
                : t("skills.changeSource.check")}
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
