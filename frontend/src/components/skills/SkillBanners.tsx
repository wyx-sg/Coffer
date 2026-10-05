// frontend/src/components/skills/SkillBanners.tsx
// The Git source's and the copies' banners under the open skill's tab strip, one
// per attention item (lib/skills/attention.ts): a folder is in the way of an
// agent's link (Review…), the Git source cannot be reached (Check again, then Ask
// an agent ▾ and its "?" — a network, VPN or credential problem on this
// machine), an update is waiting (SkillUpdateBanner: the hand-off to an
// agent, I merged it, and ways to look at the change outside Coffer). The master
// folder's and the dependencies' banners are drawn by the detail pane itself
// (SkillMasterBanner, SkillDependencyBanners). A fix button lives in the banner
// that states the problem.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Info, RefreshCw } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useCheckSkillSource } from "@/lib/hooks/useSkills";
import type { SkillAttention } from "@/lib/skills/attention";
import { repoLabel } from "@/components/skills/skillSourceHelpers";
import { clockTime } from "@/lib/skills/format";
import { SkillUpdateBanner } from "./SkillUpdateBanner";

interface Props {
  skill: SkillOut;
  items: SkillAttention[];
  /** Review… on a folder in the way: opens the compare dialog for that copy. */
  onReviewCopy: (entry: SkillDriftEntry) => void;
}

function Banner({
  tone,
  title,
  children,
  action,
  testId,
}: {
  tone: "info" | "warning";
  title: string;
  children: ReactNode;
  action?: ReactNode;
  testId: string;
}) {
  const Icon = tone === "warning" ? AlertTriangle : Info;
  return (
    <Alert variant={tone} data-testid={testId}>
      <Icon aria-hidden />
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>{children}</AlertDescription>
        </div>
        {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
      </div>
    </Alert>
  );
}

export function SkillBanners({ skill, items, onReviewCopy }: Props) {
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
          case "sourceUnreachable":
            return (
              <Banner
                key="unreachable"
                tone="warning"
                testId="skill-banner-unreachable"
                title={t("skills.banner.unreachableTitle", { repo: src ? repoLabel(src.url) : "" })}
                action={
                  <>
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
                    {/* A network, VPN or credential problem on this machine: an agent can look. */}
                    <AgentHandoff
                      size="sm"
                      prompt={t("skills.banner.unreachablePrompt", {
                        name: skill.name,
                        url: src?.url ?? "",
                        error: status?.error ?? "",
                      })}
                    />
                  </>
                }
              >
                {t("skills.banner.unreachableBody", {
                  time: status?.checked_at ? clockTime(status.checked_at, lang) : "—",
                  error: status?.error ?? "",
                })}
              </Banner>
            );
          case "updateAvailable":
            return src ? <SkillUpdateBanner key="update" skill={skill} source={src} /> : null;
        }
      })}
    </>
  );
}
