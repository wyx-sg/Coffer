// src/components/skills/SkillGitSource.tsx
// A Git-imported skill's Source block: repository, folder, pinned commit, check status, Check now, and the update banner that opens the review.
//
// Spec skill-manager "Update a Git-imported skill from its source": a check
// writes nothing; an update shows as available with its commit range; an
// unreachable source is reported with git's message and the time of the last
// successful check, and the skill keeps working from its pinned copy.
import { useState, type ReactNode } from "react";
import { AlertTriangle, ArrowUpCircle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import type { GitImportSource, SkillOut, SkillSourceStatus } from "@/lib/api/skills";
import { useCheckSkillSource } from "@/lib/hooks/useSkills";
import { formatDateTime } from "@/lib/utils";
import { repoLabel, shortCommit } from "./skillSourceHelpers";
import { SkillUpdateDialog } from "./SkillUpdateDialog";

interface Props {
  skill: SkillOut;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid min-h-9 grid-cols-[110px_minmax(0,1fr)] items-center gap-3 border-t border-border-subtle py-1 first:border-t-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-text">
        {children}
      </span>
    </div>
  );
}

function StatusValue({ status }: { status: SkillSourceStatus | null }) {
  const { t } = useTranslation();
  if (!status || !status.checked_at) {
    return <StatusWord tone="off">{t("skillSources.source.notChecked")}</StatusWord>;
  }
  if (status.error) {
    return (
      <StatusWord tone="err">
        {t("skillSources.source.unreachableSince", { time: formatDateTime(status.checked_at) })}
      </StatusWord>
    );
  }
  if (status.update_available) {
    return (
      <>
        <StatusWord tone="warn">{t("skillSources.source.updateAvailable")}</StatusWord>
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
        {t("skillSources.source.checkedAt", { time: formatDateTime(status.checked_at) })}
      </span>
    </>
  );
}

function Banner({
  tone,
  title,
  children,
  action,
}: {
  tone: "info" | "error";
  title: string;
  children: ReactNode;
  action: ReactNode;
}) {
  const Icon = tone === "info" ? ArrowUpCircle : AlertTriangle;
  return (
    <div
      role="status"
      className={
        tone === "info"
          ? "flex items-start gap-2.5 rounded-lg bg-accent-soft px-3 py-2.5"
          : "flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
      }
    >
      <Icon
        aria-hidden
        className={
          tone === "info"
            ? "mt-px size-[15px] shrink-0 text-accent-text"
            : "mt-px size-[15px] shrink-0 text-danger"
        }
      />
      <div className="flex min-w-0 flex-col gap-[3px]">
        <span className="text-sm font-label text-text">{title}</span>
        <div className="flex flex-col gap-0.5 text-xs leading-[1.45] text-text-muted">
          {children}
        </div>
      </div>
      <span className="ml-auto flex shrink-0 gap-1.5">{action}</span>
    </div>
  );
}

function GitSourceBlock({ skill, source }: { skill: SkillOut; source: GitImportSource }) {
  const { t } = useTranslation();
  const check = useCheckSkillSource();
  const [reviewing, setReviewing] = useState(false);
  const status = skill.source_status;
  const repo = repoLabel(source.url);
  const ref = source.ref ?? t("skillSources.source.defaultBranch");
  const checking = check.isPending;
  const runCheck = () => check.mutate(skill.uid);

  return (
    <div className="flex flex-col gap-3.5">
      {status?.error ? (
        <Banner
          tone="error"
          title={t("skillSources.source.unreachableTitle", { repo })}
          action={
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={checking}
              onClick={runCheck}
            >
              {checking ? t("skillSources.source.checking") : t("skillSources.source.checkAgain")}
            </Button>
          }
        >
          <span className="whitespace-pre-wrap break-words font-mono">{status.error}</span>
          <span>
            {status.last_success_at
              ? t("skillSources.source.lastSuccess", {
                  time: formatDateTime(status.last_success_at),
                })
              : t("skillSources.source.neverSucceeded")}
          </span>
          <span>{t("skillSources.source.unreachableBody")}</span>
        </Banner>
      ) : status?.update_available ? (
        <Banner
          tone="info"
          title={t("skillSources.source.bannerTitle", { repo })}
          action={
            <Button type="button" size="sm" onClick={() => setReviewing(true)}>
              {t("skillSources.source.review")}
            </Button>
          }
        >
          <span>
            {t("skillSources.source.bannerBody", {
              ref,
              count: status.commits_ahead,
              pinned: shortCommit(source.commit),
              files: status.files_changed,
            })}
          </span>
        </Banner>
      ) : null}

      <section aria-label={t("skillSources.source.title")} className="flex min-w-0 flex-col gap-2">
        <div className="flex min-h-[26px] items-center gap-2">
          <h3 className="text-sm font-semibold text-text">{t("skillSources.source.title")}</h3>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto"
            disabled={checking}
            onClick={runCheck}
          >
            <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
            {checking ? t("skillSources.source.checking") : t("skillSources.source.checkNow")}
          </Button>
        </div>
        <div className="flex flex-col">
          <Row label={t("skillSources.source.repository")}>
            <span className="min-w-0 break-all font-mono text-xs">{source.url}</span>
          </Row>
          <Row label={t("skillSources.source.folder")}>
            {source.subpath ? (
              <span className="font-mono text-xs">{source.subpath}</span>
            ) : (
              <span className="text-text-muted">{t("skillSources.source.folderTop")}</span>
            )}
          </Row>
          <Row label={t("skillSources.source.pinned")}>
            <span className="font-mono text-xs">{shortCommit(source.commit)}</span>
            <span className="text-xs text-text-muted">{ref}</span>
          </Row>
          <Row label={t("skillSources.source.status")}>
            <StatusValue status={status} />
          </Row>
        </div>
      </section>

      <SkillUpdateDialog skill={skill} open={reviewing} onOpenChange={setReviewing} />
    </div>
  );
}

export function SkillGitSourcePanel({ skill }: Props) {
  if (skill.source.type !== "git_import") return null;
  return <GitSourceBlock skill={skill} source={skill.source} />;
}
