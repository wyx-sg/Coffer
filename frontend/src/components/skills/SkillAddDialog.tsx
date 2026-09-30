// src/components/skills/SkillAddDialog.tsx
// The Add skill dialog: a folder, an archive or a Git repository is staged, what it holds is shown, and only the confirm adds anything.
//
// Spec skill-manager "Cover skill management on REST, the CLI and the web" (the
// dialog), "Import a skill from a local path", "Add skills from an archive" and
// "Add skills from a Git repository". The stage (useSkillAddStage) is cancelled whenever it leaves the screen.
import { useEffect, useRef, useState, type DragEvent } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useApplySkillReach } from "@/lib/hooks/useSkillCopies";
import { EVERY_AGENT, type SkillReachDraft } from "@/lib/skills/reach";
import { SkillAddReach } from "./SkillAddReach";
import { SkillAddRefusal } from "./SkillAddRefusal";
import { errorHandoff } from "@/lib/api/errorHandoff";
import {
  SkillAddArchiveField,
  SkillAddFolderField,
  SkillAddGitFields,
  type GitLocation,
} from "./SkillAddSourceFields";
import { SkillAddSourceSwitch, type SkillAddSource } from "./SkillAddSourceSwitch";
import { useSkillAddStage } from "./SkillAddStage";
import { SkillFoundList } from "./SkillFoundList";
import { cleanPath, gitHost, isArchiveFile } from "./skillSourceHelpers";

export type { SkillAddSource } from "./SkillAddSourceSwitch";

const NO_GIT: GitLocation = { url: "", ref: "", path: "" };

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The source the dialog opens on; Folder when omitted. */
  initialSource?: SkillAddSource;
}

export function SkillAddDialog({ open, onOpenChange, initialSource }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const s = useSkillAddStage();
  const { discard } = s;

  const [source, setSource] = useState<SkillAddSource>(initialSource ?? "folder");
  const [folder, setFolder] = useState("");
  const [archive, setArchive] = useState<File | null>(null);
  const [git, setGit] = useState<GitLocation>(NO_GIT);
  const [reach, setReach] = useState<SkillReachDraft>(EVERY_AGENT);
  const applyReach = useApplySkillReach();
  // The folder last looked at, so leaving the field after a pick does not look twice.
  const lookedFolder = useRef<string | null>(null);

  // A fresh dialog each time it opens; closing cancels what was staged.
  useEffect(() => {
    if (open) {
      setSource(initialSource ?? "folder");
      setFolder("");
      setArchive(null);
      setGit(NO_GIT);
      setReach(EVERY_AGENT);
      lookedFolder.current = null;
    } else {
      discard();
    }
  }, [open, initialSource, discard]);

  const handleOpenChange = (next: boolean) => {
    if (!next) discard();
    onOpenChange(next);
  };

  const shown = !!(s.stage || s.stageError);

  const lookAtFolder = (path: string) => {
    if (lookedFolder.current === path && (shown || s.looking)) return;
    lookedFolder.current = path;
    void s.look({ kind: "folder", path });
  };

  const changeFolder = (text: string) => {
    // A stage answers for the folder it looked at, not the one now typed.
    if (shown && cleanPath(text) !== lookedFolder.current) discard();
    setFolder(text);
  };

  const pickArchive = (file: File) => {
    setArchive(file);
    void s.look({ kind: "archive", file });
  };

  const changeGit = (next: GitLocation) => {
    if (shown) discard();
    setGit(next);
  };

  const cloneGit = () => {
    const url = git.url.trim();
    if (!url) return;
    void s.look({ kind: "git", url, ref: git.ref.trim() || null, path: git.path.trim() || null });
  };

  const switchSource = (next: SkillAddSource) => {
    discard();
    setSource(next);
  };

  const confirm = async () => {
    const added = await s.confirm();
    if (!added) return;
    if (reach.mode !== "everywhere") {
      await applyReach
        .mutateAsync({ uids: added.map((a) => a.uid), mode: reach.mode, scope: reach.scope })
        .catch(() => undefined);
    }
    handleOpenChange(false);
    if (added[0]) navigate(`/skills/${encodeURIComponent(added[0].name)}`);
  };

  const onDrop = (e: DragEvent) => {
    const file = e.dataTransfer?.files?.[0];
    if (!file || !isArchiveFile(file)) return;
    e.preventDefault();
    if (source !== "archive") switchSource("archive");
    pickArchive(file);
  };

  const single = s.stage?.skills.length === 1 ? s.chosen[0] : undefined;
  const primaryLabel = s.confirming
    ? t("skillSources.add.adding")
    : single?.taken
      ? t("skillSources.add.replaceOne", { name: single.name })
      : s.chosen.length > 1
        ? t("skillSources.add.addMany", { count: s.chosen.length })
        : t("skillSources.add.addOne");
  const gitNeedsClone = source === "git" && !s.stage;
  const unreachable =
    source === "git" &&
    s.stageError instanceof ApiError &&
    s.stageError.code === "SKILL_SOURCE_UNREACHABLE" &&
    !errorHandoff(s.stageError);
  const cloning = source === "git" && s.looking;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[calc(100vh-4rem)] max-w-[520px] overflow-y-auto"
        onDragOver={(e) => {
          if (e.dataTransfer?.types?.includes("Files")) e.preventDefault();
        }}
        onDrop={onDrop}
      >
        <DialogHeader>
          <DialogTitle>{t("skillSources.add.title")}</DialogTitle>
          <DialogDescription>
            {source === "archive" && (s.stage?.skills.length ?? 0) > 1
              ? t("skillSources.add.subtitle.archiveMany")
              : t(`skillSources.add.subtitle.${source}`)}
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (gitNeedsClone) cloneGit();
            else void confirm();
          }}
        >
          <SkillAddSourceSwitch value={source} onChange={switchSource} />
          {source === "folder" ? (
            <SkillAddFolderField value={folder} onChange={changeFolder} onLook={lookAtFolder} />
          ) : source === "archive" ? (
            <SkillAddArchiveField file={archive} onPick={pickArchive} />
          ) : (
            <SkillAddGitFields
              value={git}
              onChange={changeGit}
              disabled={cloning}
              urlError={
                unreachable ? t("skillSources.git.unreachable", { host: gitHost(git.url) }) : null
              }
            />
          )}
          {s.looking ? (
            <p role="status" className="flex items-center gap-2 text-xs text-text-muted">
              <Loader2 aria-hidden className="size-3.5 animate-spin" />
              {source === "git"
                ? t("skillSources.git.cloningLine", { url: git.url.trim() })
                : t("skillSources.add.looking")}
            </p>
          ) : null}
          {s.stageError && !unreachable ? (
            <SkillAddRefusal
              error={s.stageError}
              action={
                source === "archive" ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => document.getElementById("skill-add-archive")?.click()}
                  >
                    {t("skillSources.archive.chooseAnother")}
                  </Button>
                ) : undefined
              }
            />
          ) : null}
          {s.stage ? (
            <SkillFoundList stage={s.stage} selected={s.selected} onToggle={s.toggle} />
          ) : null}
          <SkillAddReach value={reach} onChange={setReach} />
          {s.confirmError ? (
            <p role="alert" className="text-xs text-danger">
              {translateApiError(t, s.confirmError)}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            {gitNeedsClone ? (
              <Button type="submit" disabled={cloning || !git.url.trim()}>
                {cloning
                  ? t("skillSources.git.cloning")
                  : s.stageError
                    ? t("skillSources.git.retry")
                    : t("skillSources.git.clone")}
              </Button>
            ) : (
              <Button type="submit" disabled={s.chosen.length === 0 || s.confirming}>
                {primaryLabel}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
