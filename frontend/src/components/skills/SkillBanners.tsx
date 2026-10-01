// frontend/src/components/skills/SkillBanners.tsx
// The banners above the open skill's tabs, one per attention item
// (lib/skills/attention.ts), most urgent first: the master folder is gone, a
// folder is in the way of an agent's link (Review…), a command it needs is
// missing or not logged in, a secret it needs is not set (Open Secrets), its
// Git source cannot be reached (Check again), an
// update is waiting (Review update…). Each banner carries at most one action.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertCircle, AlertTriangle, Info, RefreshCw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useCheckSkillSource } from "@/lib/hooks/useSkills";
import type { SkillAttention } from "@/lib/skills/attention";
import { repoLabel } from "@/components/skills/skillSourceHelpers";
import { clockTime, folderLabel } from "@/lib/skills/format";
import { joinNames } from "@/lib/skills/names";

interface Props {
  skill: SkillOut;
  items: SkillAttention[];
  /** Review… on a folder in the way: opens the compare dialog for that copy. */
  onReviewCopy: (entry: SkillDriftEntry) => void;
  /** Review update… on a Git skill with an update waiting. */
  onReviewUpdate: () => void;
}

function Banner({
  tone,
  title,
  children,
  action,
  testId,
}: {
  tone: "info" | "warning" | "error";
  title: string;
  children: ReactNode;
  action?: ReactNode;
  testId: string;
}) {
  const Icon = tone === "error" ? AlertCircle : tone === "warning" ? AlertTriangle : Info;
  return (
    <Alert variant={tone} data-testid={testId}>
      <Icon aria-hidden />
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>{children}</AlertDescription>
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
    </Alert>
  );
}

export function SkillBanners({ skill, items, onReviewCopy, onReviewUpdate }: Props) {
  const { t, i18n } = useTranslation();
  const { data: agents = [] } = useAgents();
  const check = useCheckSkillSource();
  const lang = i18n.language;
  const agentLabel = (name: string) => agents.find((a) => a.name === name)?.display_name ?? name;
  const src = skill.source.type === "git_import" ? skill.source : null;
  const status = skill.source_status;

  return (
    <>
      {items.map((item) => {
        switch (item.kind) {
          case "masterMissing":
            return (
              <Banner
                key="master"
                tone="error"
                testId="skill-banner-master"
                title={t("skills.banner.masterTitle")}
              >
                {t(skill.enabled ? "skills.banner.masterBodyOn" : "skills.banner.masterBodyOff", {
                  path: abbreviateHomePath(skill.master_path),
                })}
              </Banner>
            );
          case "folderInWay":
            return (
              <Banner
                key={`way:${item.agentName}`}
                tone="warning"
                testId="skill-banner-folder"
                title={t("skills.banner.folderTitle", { agent: agentLabel(item.agentName) })}
                action={
                  <Button variant="outline" size="sm" onClick={() => onReviewCopy(item.entry)}>
                    {t("skills.review")}
                  </Button>
                }
              >
                {t("skills.banner.folderBody", {
                  path: abbreviateHomePath(item.entry.target_path),
                  name: skill.name,
                })}
              </Banner>
            );
          case "requires": {
            const parts = [
              item.missing.length > 0
                ? t("skills.banner.requiresMissingPart", {
                    count: item.missing.length,
                    commands: joinNames(item.missing, lang),
                  })
                : null,
              item.loggedOut.length > 0
                ? t("skills.banner.requiresLoginPart", {
                    count: item.loggedOut.length,
                    commands: joinNames(item.loggedOut, lang),
                  })
                : null,
              item.outdated.length > 0
                ? t("skills.banner.requiresOldPart", {
                    count: item.outdated.length,
                    commands: joinNames(item.outdated, lang),
                  })
                : null,
            ].filter(Boolean);
            const heads = [
              item.missing.length > 0
                ? t("skills.banner.requiresMissing", { count: item.missing.length })
                : null,
              item.loggedOut.length > 0
                ? t("skills.banner.requiresLogin", { count: item.loggedOut.length })
                : null,
              item.outdated.length > 0
                ? t("skills.banner.requiresOld", { count: item.outdated.length })
                : null,
            ].filter(Boolean);
            return (
              <Banner
                key="requires"
                tone="warning"
                testId="skill-banner-requires"
                title={heads.join(", ")}
              >
                {`${parts.join("; ")}.`}
              </Banner>
            );
          }
          case "secrets":
            // Setting a secret is the person's own task on the Secrets page —
            // no hand-off, and never a value here.
            return (
              <Banner
                key="secrets"
                tone="warning"
                testId="skill-banner-secrets"
                title={t("skills.banner.secretsTitle", { count: item.missing.length })}
                action={
                  <Button asChild variant="outline" size="sm">
                    <Link to="/secrets">{t("skills.requires.openSecrets")}</Link>
                  </Button>
                }
              >
                {`${item.missing.map((name) => t("skills.requires.secretMissing", { name })).join("; ")}.`}
              </Banner>
            );
          case "sourceUnreachable":
            return (
              <Banner
                key="unreachable"
                tone="warning"
                testId="skill-banner-unreachable"
                title={t("skills.banner.unreachableTitle", { repo: src ? repoLabel(src.url) : "" })}
                action={
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={check.isPending}
                    onClick={() => check.mutate(skill.uid)}
                  >
                    <RefreshCw
                      aria-hidden
                      className={check.isPending ? "animate-spin" : undefined}
                    />
                    {t("skills.delivery.checkAgain")}
                  </Button>
                }
              >
                {t("skills.banner.unreachableBody", {
                  time: status?.checked_at ? clockTime(status.checked_at, lang) : "—",
                  error: status?.error ?? "",
                })}
              </Banner>
            );
          case "updateAvailable":
            return (
              <Banner
                key="update"
                tone="info"
                testId="skill-banner-update"
                title={t("skills.banner.updateTitle", { repo: src ? repoLabel(src.url) : "" })}
                action={
                  <Button variant="outline" size="sm" onClick={onReviewUpdate}>
                    {t("skills.banner.reviewUpdate")}
                  </Button>
                }
              >
                {t("skills.banner.updateBody", {
                  ref: src?.ref ?? t("skills.banner.defaultBranch"),
                  count: status?.commits_ahead ?? 0,
                  commit: src?.commit.slice(0, 7) ?? "",
                  files: status?.files_changed ?? 0,
                  folder: (src && folderLabel(src.subpath)) ?? t("skills.banner.repoTop"),
                })}
              </Banner>
            );
        }
      })}
    </>
  );
}
