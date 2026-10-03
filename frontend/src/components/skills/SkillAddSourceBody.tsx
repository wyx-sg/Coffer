// src/components/skills/SkillAddSourceBody.tsx
// The Add skill dialog's middle: the source's fields, the progress row while a source is being looked at, why it was refused, and what it holds.
//
// A folder or an archive is refused in red under its own field; a Git source
// that is refused because of this machine (git missing, a clone that failed) is
// a problem block with the hand-off, under the fields (canvas 4.3.33, 4.3.38, 4.3.51-53).
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { useSkillAddStage } from "./SkillAddStage";
import { SkillAddRefusal, SkillGitProblem } from "./SkillAddRefusal";
import {
  SkillAddArchiveField,
  SkillAddFolderField,
  SkillAddGitFields,
  type GitLocation,
} from "./SkillAddSourceFields";
import type { SkillAddSource } from "./SkillAddSourceSwitch";
import { SkillFoundList } from "./SkillFoundList";
import { cleanPath, isMachineProblem, repoName } from "./skillSourceHelpers";

interface Props {
  source: SkillAddSource;
  stage: ReturnType<typeof useSkillAddStage>;
  folder: string;
  onFolder: (text: string) => void;
  onLookFolder: (path: string) => void;
  onUseFolder: (path: string) => void;
  archive: File | null;
  onArchive: (file: File) => void;
  git: GitLocation;
  onGit: (next: GitLocation) => void;
}

/** The last segment of a folder path, for "No SKILL.md in {{file}}". */
const lastSegment = (path: string) => cleanPath(path).replace(/\/+$/, "").split("/").pop() ?? path;

export function SkillAddSourceBody(p: Props) {
  const { t } = useTranslation();
  const { stage: s, source } = p;
  const refusal = s.stageError ? (
    <SkillAddRefusal
      error={s.stageError}
      subject={
        source === "archive"
          ? (p.archive?.name ?? "")
          : source === "git"
            ? repoName(p.git.url)
            : lastSegment(p.folder)
      }
      onUseFolder={source === "folder" ? p.onUseFolder : undefined}
    />
  ) : null;
  const gitProblem = source === "git" && isMachineProblem(s.stageError);
  const cloning = source === "git" && s.looking;
  return (
    <>
      {source === "folder" ? (
        <SkillAddFolderField
          value={p.folder}
          onChange={p.onFolder}
          onLook={p.onLookFolder}
          error={refusal}
        />
      ) : source === "archive" ? (
        <SkillAddArchiveField file={p.archive} onPick={p.onArchive} error={refusal} />
      ) : (
        <SkillAddGitFields value={p.git} onChange={p.onGit} disabled={cloning} />
      )}
      {source === "git" && s.stageError ? (
        gitProblem ? (
          <SkillGitProblem error={s.stageError} url={p.git.url} />
        ) : (
          refusal
        )
      ) : null}
      {s.looking ? (
        <p
          role="status"
          className="flex items-center gap-2 rounded-lg border border-border px-3 py-2.5 text-sm text-text"
        >
          <Loader2 aria-hidden className="size-3.5 animate-spin text-text-muted" />
          {source === "git"
            ? t("skillSources.git.cloningLine", { repo: repoName(p.git.url) })
            : t("skillSources.add.looking")}
        </p>
      ) : null}
      {s.stage ? (
        <SkillFoundList stage={s.stage} selected={s.selected} onToggle={s.toggle} />
      ) : null}
    </>
  );
}
