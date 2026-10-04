// src/components/skills/SkillGitSource.tsx
// A Git-imported skill's Source bar (canvas 4.3.17, 4.3.21): one line above the
// files — "Pinned a1b2c3d on main · Sep 18", and at the right when it was last
// checked, Check again and Change source…. The banners that say an update is
// waiting or the source can't be reached sit above the tabs (SkillBanners);
// when the source is unreachable the banner carries Check again, so this bar
// drops it and the "Checked at" beside it.
//
// Spec skill-manager "Update a Git-imported skill from its source": a check
// writes nothing; an update shows as available with its commit range; an
// unreachable source is reported and the skill keeps working from its pinned
// copy. Change source… checks the new source and shows the change before
// anything is replaced (SkillChangeSourceDialog).
import { useState } from "react";
import { GitBranch, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { GitImportSource, SkillOut } from "@/lib/api/skills";
import { useCheckSkillSource } from "@/lib/hooks/useSkills";
import { clockTime } from "@/lib/skills/format";
import { SkillChangeSourceDialog } from "./SkillChangeSourceDialog";
import { shortCommit } from "./skillSourceHelpers";

interface Props {
  skill: SkillOut;
}

/** "Sep 18": the day the skill was pinned or last moved to its commit. */
function dayLabel(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

function GitSourceBar({ skill, source }: { skill: SkillOut; source: GitImportSource }) {
  const { t, i18n } = useTranslation();
  const check = useCheckSkillSource();
  const [changing, setChanging] = useState(false);
  const checking = check.isPending;
  const status = skill.source_status;
  const unreachable = Boolean(status?.error);
  const pinnedOn = dayLabel(skill.last_synced_from_source_at ?? skill.created_at, i18n.language);

  return (
    <div className="flex min-h-8 items-center gap-2" data-testid="skill-source-bar">
      <GitBranch className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
      <span className="min-w-0 truncate text-xs text-text-muted">
        {t("skillSources.source.pinned")}{" "}
        <span className="font-mono">{shortCommit(source.commit)}</span>{" "}
        {t("skillSources.source.on")}{" "}
        <span className="font-mono">{source.ref ?? t("skillSources.source.defaultBranch")}</span>
        {pinnedOn ? ` · ${pinnedOn}` : ""}
      </span>
      <span className="ml-auto flex shrink-0 items-center gap-1">
        {!unreachable && status?.checked_at ? (
          <span className="text-xs text-text-subtle">
            {t("skillSources.source.checkedAt", {
              time: clockTime(status.checked_at, i18n.language),
            })}
          </span>
        ) : null}
        {unreachable ? null : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-text-muted"
            disabled={checking}
            onClick={() => check.mutate(skill.uid)}
          >
            <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
            {checking ? t("skillSources.source.checking") : t("skillSources.source.checkAgain")}
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-text-muted"
          onClick={() => setChanging(true)}
        >
          {t("skills.source.change")}
        </Button>
      </span>
      <SkillChangeSourceDialog skill={skill} open={changing} onOpenChange={setChanging} />
    </div>
  );
}

export function SkillGitSourcePanel({ skill }: Props) {
  if (skill.source.type !== "git_import") return null;
  return <GitSourceBar skill={skill} source={skill.source} />;
}
