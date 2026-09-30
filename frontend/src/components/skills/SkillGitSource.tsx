// src/components/skills/SkillGitSource.tsx
// A Git-imported skill's Source block (canvas 4.3.17): repository, folder,
// pinned commit and status, with Check now and Change source…. The banners
// that say an update is waiting or the source can't be reached sit above the
// tabs (SkillBanners); this block is the reference under them.
//
// Spec skill-manager "Update a Git-imported skill from its source": a check
// writes nothing; an update shows as available with its commit range; an
// unreachable source is reported and the skill keeps working from its pinned
// copy. Change source… checks the new source and shows the change before
// anything is replaced (SkillChangeSourceDialog).
import { useState, type ReactNode } from "react";
import { Pencil, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import type { GitImportSource, SkillOut, SkillSourceStatus } from "@/lib/api/skills";
import { useCheckSkillSource } from "@/lib/hooks/useSkills";
import { clockTime, folderLabel } from "@/lib/skills/format";
import { SkillChangeSourceDialog } from "./SkillChangeSourceDialog";
import { shortCommit } from "./skillSourceHelpers";

interface Props {
  skill: SkillOut;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid min-h-11 grid-cols-[120px_minmax(0,1fr)] items-center gap-3 border-t border-border-subtle py-1.5">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-text">
        {children}
      </span>
    </div>
  );
}

function StatusValue({ status }: { status: SkillSourceStatus | null }) {
  const { t, i18n } = useTranslation();
  if (!status || !status.checked_at) {
    return <StatusWord tone="off">{t("skillSources.source.notChecked")}</StatusWord>;
  }
  if (status.error) {
    return (
      <>
        <StatusWord tone="warn">{t("skills.sourceUnreachable")}</StatusWord>
        <span className="text-xs text-text-muted">
          {t("skills.source.since", { time: clockTime(status.checked_at, i18n.language) })}
        </span>
      </>
    );
  }
  if (status.update_available) {
    return (
      <>
        <span className="inline-flex items-center gap-1.5 text-xs font-label text-accent-text">
          <span aria-hidden className="size-1.5 rounded-full bg-accent" />
          {t("skillSources.source.updateAvailable")}
        </span>
        <span className="text-xs text-text-muted">
          <span className="font-mono">{shortCommit(status.latest_commit)}</span>
          {" · "}
          {t("skillSources.source.commits", { count: status.commits_ahead })}
          {" · "}
          {t("skillSources.source.files", { count: status.files_changed })}
        </span>
      </>
    );
  }
  return (
    <>
      <StatusWord tone="ok">{t("skillSources.source.upToDate")}</StatusWord>
      <span className="text-xs text-text-muted">
        {t("skillSources.source.checkedAt", { time: clockTime(status.checked_at, i18n.language) })}
      </span>
    </>
  );
}

function GitSourceBlock({ skill, source }: { skill: SkillOut; source: GitImportSource }) {
  const { t } = useTranslation();
  const check = useCheckSkillSource();
  const [changing, setChanging] = useState(false);
  const checking = check.isPending;
  const folder = folderLabel(source.subpath);

  return (
    <section aria-label={t("skillSources.source.title")} className="flex min-w-0 flex-col">
      <div className="flex min-h-9 items-center gap-1">
        <h3 className="text-sm font-semibold text-text">{t("skillSources.source.title")}</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto"
          disabled={checking}
          onClick={() => check.mutate(skill.uid)}
        >
          <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
          {checking ? t("skillSources.source.checking") : t("skillSources.source.checkNow")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setChanging(true)}>
          <Pencil aria-hidden />
          {t("skills.source.change")}
        </Button>
      </div>
      <div className="flex flex-col border-b border-border-subtle">
        <Row label={t("skillSources.source.repository")}>
          <span className="min-w-0 break-all font-mono text-xs">{source.url}</span>
        </Row>
        <Row label={t("skillSources.source.folder")}>
          {folder ? (
            <span className="font-mono text-xs">{folder}</span>
          ) : (
            <span className="text-text-muted">{t("skillSources.source.folderTop")}</span>
          )}
        </Row>
        <Row label={t("skillSources.source.pinned")}>
          <span className="font-mono text-xs">{shortCommit(source.commit)}</span>
          <span className="text-xs text-text-muted">
            {source.ref ?? t("skillSources.source.defaultBranch")}
          </span>
        </Row>
        <Row label={t("skillSources.source.status")}>
          <StatusValue status={skill.source_status} />
        </Row>
      </div>

      <SkillChangeSourceDialog skill={skill} open={changing} onOpenChange={setChanging} />
    </section>
  );
}

export function SkillGitSourcePanel({ skill }: Props) {
  if (skill.source.type !== "git_import") return null;
  return <GitSourceBlock skill={skill} source={skill.source} />;
}
