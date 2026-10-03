// frontend/src/components/skills/SkillDetailHeader.tsx
// The top of the open skill in the Skills page's reading pane (canvas 4.3
// SkillHeader): a 32px icon tile tinted by the state, the skill's fixed name
// (18/650 mono — what agents load it by, and the heading), the state pill (In
// use, Off, Command missing, Tool off, Folder in the way, Source unreachable,
// Master missing), "Built-in" beside Coffer's own, and one meta line that says
// where the skill lives, led by the source type —
//   a folder or archive skill: Folder / Archive · its master folder · Updated Sep 24
//   a Git skill: Git · the repository · the folder in it · pinned <commit>
//   the built-in skill: Written by Coffer · Regenerated today at 09:02
//   a skill whose master folder is gone: Folder · its master folder · master missing
// The right side is fixed and never changes with state: Reach and the "⋯"
// menu. There is no description here — the skill's own SKILL.md has it.
import { useTranslation } from "react-i18next";
import { GitBranch, GitCommitHorizontal, Sparkle } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { SkillActionsMenu } from "@/components/skills/SkillActionsMenu";
import { StatusPill } from "@/components/status/StatusPill";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillOut } from "@/lib/api/skills";
import type { SkillStatus } from "@/lib/skills/attention";
import type { StatusTone } from "@/lib/statusTone";
import { cn } from "@/lib/utils";
import { repoLabel } from "@/components/skills/skillSourceHelpers";
import { clockTime, folderLabel, isToday, shortDay } from "@/lib/skills/format";

interface Props {
  skill: SkillOut;
  /** The state the pill names (lib/skills/attention.ts `skillStatus`). */
  status: SkillStatus;
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

const TONE: Record<SkillStatus, StatusTone> = {
  inUse: "ok",
  off: "off",
  masterMissing: "err",
  folderInWay: "warn",
  commandMissing: "warn",
  commandNotReady: "warn",
  toolOff: "warn",
  secretMissing: "warn",
  sourceUnreachable: "warn",
};

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
        <span data-testid="skill-detail-source" className="inline-flex items-center gap-1">
          <GitBranch className="size-3.5 text-text-subtle" aria-hidden />
          {t("skills.detail.sourceType.git")}
        </span>
        <Dot />
        <span className="font-mono">{repoLabel(src.url)}</span>
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
      <span data-testid="skill-detail-source">
        {t(
          src.type === "archive_import"
            ? "skills.detail.sourceType.archive"
            : "skills.detail.sourceType.folder",
        )}
      </span>
      <Dot />
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

export function SkillDetailHeader({ skill, status, onDeleted }: Props) {
  const { t } = useTranslation();
  const tone = TONE[status];
  const masterMissing = status === "masterMissing";
  return (
    <header className="flex min-w-0 items-center gap-3">
      <span
        className={cn(
          "inline-flex size-8 shrink-0 items-center justify-center rounded-lg",
          tone === "err" && "bg-danger-soft text-danger",
          tone === "warn" && "bg-warning-soft text-warning",
          (tone === "ok" || tone === "off") &&
            "border border-border-subtle bg-surface-sunken text-text-muted",
        )}
      >
        <Sparkle className="size-4" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
        <div className="flex min-w-0 items-center gap-2.5">
          <h2 className="min-w-0 truncate font-mono text-lg font-semibold">{skill.name}</h2>
          <StatusPill tone={tone} className="shrink-0">
            {t(`skills.detail.status.${status}`)}
          </StatusPill>
          {skill.builtin ? (
            <span
              data-testid="skill-builtin-badge"
              className="shrink-0 rounded-item bg-chip px-2 py-0.5 text-xs font-semibold text-text-muted"
            >
              {t("skills.builtinBadge")}
            </span>
          ) : null}
        </div>
        <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-text-muted">
          <MetaLine skill={skill} masterMissing={masterMissing} />
        </p>
      </div>
      <span className="inline-flex shrink-0 items-center gap-2">
        <ScopeControl kind="skill" uid={skill.uid} enabled={skill.enabled} scope={skill.scope} />
        <SkillActionsMenu skill={skill} onDeleted={onDeleted} />
      </span>
    </header>
  );
}
