// frontend/src/components/skills/SkillDetailHeader.tsx
// The top of the open skill in the Skills page's reading pane (canvas 4.3.01):
// its name (fixed, what agents load it by, and the heading), "Built-in" beside
// Coffer's own, the reach button and the "⋯" menu, the description, and one
// meta line that says where the skill lives —
//   a folder or archive skill: its master folder · Updated Sep 24
//   a Git skill: the repository · the folder in it · pinned <commit>
//   the built-in skill: Written by Coffer · Regenerated today at 09:02
//   a skill whose master folder is gone: its master folder · master missing
import { useTranslation } from "react-i18next";
import { AlertTriangle, GitBranch, GitCommitHorizontal, Sparkles } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { SkillActionsMenu } from "@/components/skills/SkillActionsMenu";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillOut } from "@/lib/api/skills";
import { cn } from "@/lib/utils";
import { repoLabel } from "@/components/skills/skillSourceHelpers";
import { clockTime, folderLabel, isToday, shortDay } from "@/lib/skills/format";

interface Props {
  skill: SkillOut;
  /** Its master folder is gone (a Check copies finding). */
  masterMissing?: boolean;
  onCheckCopies: () => void;
  /** Called once the delete has landed, to leave the address of a skill that is gone. */
  onDeleted: () => void;
}

function Dot() {
  return (
    <span aria-hidden className="text-text-subtle">
      ·
    </span>
  );
}

function MetaLine({ skill, masterMissing }: { skill: SkillOut; masterMissing: boolean }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const when = isToday(skill.updated_at)
    ? t("skills.detail.todayAt", { time: clockTime(skill.updated_at, lang) })
    : shortDay(skill.updated_at, lang);
  const src = skill.source;

  if (src.type === "builtin") {
    return (
      <>
        <span data-testid="skill-detail-source">{t("skills.detail.source.builtin")}</span>
        <Dot />
        <span>{t("skills.detail.regenerated", { when })}</span>
      </>
    );
  }
  if (src.type === "git_import") {
    const folder = folderLabel(src.subpath);
    return (
      <>
        <span
          data-testid="skill-detail-source"
          className="inline-flex items-center gap-1 font-mono"
        >
          <GitBranch className="size-3.5 text-text-subtle" aria-hidden />
          {repoLabel(src.url)}
        </span>
        {folder ? (
          <>
            <Dot />
            <span className="font-mono">{folder}</span>
          </>
        ) : null}
        <Dot />
        <span className="inline-flex items-center gap-1">
          <GitCommitHorizontal className="size-3.5 text-text-subtle" aria-hidden />
          {t("skills.detail.pinned")}
          <span className="font-mono">{src.commit.slice(0, 7)}</span>
        </span>
      </>
    );
  }
  return (
    <>
      <span
        className={cn("font-mono", masterMissing && "text-danger")}
        data-testid="skill-master-path"
      >
        {abbreviateHomePath(skill.master_path)}
      </span>
      <Dot />
      {masterMissing ? (
        <span className="text-danger">{t("skills.detail.masterMissing")}</span>
      ) : (
        <span>{t("skills.detail.updated", { when })}</span>
      )}
    </>
  );
}

export function SkillDetailHeader({
  skill,
  masterMissing = false,
  onCheckCopies,
  onDeleted,
}: Props) {
  const { t } = useTranslation();
  return (
    <header className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2.5">
        <span
          className={cn(
            "inline-flex size-[30px] shrink-0 items-center justify-center rounded-lg",
            masterMissing
              ? "bg-danger-soft text-danger"
              : "border border-border-subtle bg-surface-sunken text-text-muted",
          )}
        >
          {masterMissing ? (
            <AlertTriangle className="size-4" strokeWidth={1.75} aria-hidden />
          ) : (
            <Sparkles className="size-4" strokeWidth={1.75} aria-hidden />
          )}
        </span>
        <h2 className="min-w-0 truncate font-mono text-lg font-bold">{skill.name}</h2>
        {skill.builtin ? (
          <span
            data-testid="skill-builtin-badge"
            className="rounded-sm bg-chip px-1.5 py-0.5 text-2xs font-label text-text-muted"
          >
            {t("skills.builtinBadge")}
          </span>
        ) : null}
        <span className="ml-auto inline-flex items-center gap-1.5">
          <ScopeControl kind="skill" uid={skill.uid} enabled={skill.enabled} scope={skill.scope} />
          <SkillActionsMenu skill={skill} onCheckCopies={onCheckCopies} onDeleted={onDeleted} />
        </span>
      </div>
      {skill.description ? (
        <p className="max-w-measure text-sm leading-normal text-text-muted">{skill.description}</p>
      ) : null}
      <p className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
        <MetaLine skill={skill} masterMissing={masterMissing} />
      </p>
    </header>
  );
}
