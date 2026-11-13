// frontend/src/components/skills/SkillDependencyBanners.tsx
// The banners for what the skill depends on (lib/skills/attention.ts), under
// the tab strip of the open skill: a command it needs that is missing, not
// logged in or too old — one banner with one hand-off for all of them (4.3.10);
// a tool it calls (MCP server or custom-tool group) that is off or failing,
// with a button to that tool's page (4.3.56) — turning it on is the person's,
// so no hand-off; a secret it needs that is not set (Open Secrets). The skill
// is still delivered in every case.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { SkillBannerFrame } from "@/components/skills/SkillBannerFrame";
import { Button } from "@/components/ui/button";
import { agentTypeLabel } from "@/lib/agents/display";
import type { SkillOut } from "@/lib/api/skills";
import { useClis } from "@/lib/hooks/useClis";
import type { SkillAttention } from "@/lib/skills/attention";
import { joinNames } from "@/lib/skills/names";
import { toolHref } from "@/lib/skills/toolLinks";

interface Props {
  skill: SkillOut;
  items: SkillAttention[];
}

function CommandsBanner({
  skill,
  item,
}: {
  skill: SkillOut;
  item: Extract<SkillAttention, { kind: "requires" }>;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const clis = useClis().data?.items ?? [];
  const title = t("skills.banner.requiresMissingPart", {
    count: item.missing.length,
    commands: joinNames(item.missing, lang),
  });
  // One hand-off for every command that needs the person, as the daemon wrote them.
  const wanted = new Set(item.missing);
  const prompt = clis
    .filter((c) => wanted.has(c.command) && c.handoff)
    .map((c) => c.handoff?.prompt)
    .join("\n\n");
  return (
    <SkillBannerFrame
      tone="warning"
      testId="skill-banner-requires"
      title={title}
      actions={prompt ? <AgentHandoff prompt={prompt} size="sm" /> : null}
    >
      {t("skills.banner.requiresBody", { name: skill.name })}
    </SkillBannerFrame>
  );
}

export function SkillDependencyBanners({ skill, items }: Props) {
  const { t } = useTranslation();
  return (
    <>
      {items.map((item) => {
        if (item.kind === "requires")
          return <CommandsBanner key="requires" skill={skill} item={item} />;
        if (item.kind === "toolOff") {
          return item.tools.map((tool) => (
            <SkillBannerFrame
              key={`tool:${tool.uid}`}
              tone="warning"
              testId="skill-banner-tool"
              title={t(`skills.banner.tool.${tool.status === "failing" ? "failing" : "off"}`, {
                tool: tool.name,
                name: skill.name,
              })}
              actions={
                <Button asChild variant="outline" size="sm">
                  <Link to={toolHref(tool)}>
                    {t("skills.banner.openTool", { tool: tool.name })}
                  </Link>
                </Button>
              }
            >
              {tool.status === "failing" && tool.why
                ? tool.why
                : t(
                    `skills.banner.toolBody.${tool.status === "failing" ? "failing" : "off"}.${tool.kind}`,
                    {
                      tool: tool.name,
                      name: skill.name,
                    },
                  )}
            </SkillBannerFrame>
          ));
        }
        if (item.kind === "toolNotShared") {
          return item.tools.map((tool) => (
            <SkillBannerFrame
              key={`tool-reach:${tool.uid}`}
              tone="warning"
              testId="skill-banner-tool-reach"
              title={t("skills.banner.toolNotShared", {
                tool: tool.name,
                name: skill.name,
                agents: (tool.missing_agent_names ?? []).map(agentTypeLabel).join(", "),
              })}
              actions={
                <Button asChild variant="outline" size="sm">
                  <Link to={toolHref(tool)}>
                    {t("skills.banner.openTool", { tool: tool.name })}
                  </Link>
                </Button>
              }
            >
              {t("skills.banner.toolNotSharedBody", { tool: tool.name, name: skill.name })}
            </SkillBannerFrame>
          ));
        }
        if (item.kind === "skillNotShared") {
          return item.skills.map((dep) => (
            <SkillBannerFrame
              key={`skill:${dep.name}`}
              tone="warning"
              testId="skill-banner-skill"
              title={t("skills.banner.skillNotShared", {
                dep: dep.name,
                name: skill.name,
                agents: dep.missing_agent_names.map(agentTypeLabel).join(", "),
              })}
              actions={
                <Button asChild variant="outline" size="sm">
                  <Link to={`/skills/${encodeURIComponent(dep.name)}`}>
                    {t("skills.banner.openSkill", { name: dep.name })}
                  </Link>
                </Button>
              }
            >
              {t("skills.banner.skillNotSharedBody", { dep: dep.name, name: skill.name })}
            </SkillBannerFrame>
          ));
        }
        if (item.kind === "secrets") {
          return (
            <SkillBannerFrame
              key="secrets"
              tone="warning"
              testId="skill-banner-secrets"
              title={t("skills.banner.secretsTitle", { count: item.missing.length })}
              actions={
                <Button asChild variant="outline" size="sm">
                  <Link to="/secrets">{t("skills.requires.openSecrets")}</Link>
                </Button>
              }
            >
              {`${item.missing.map((name) => t("skills.requires.secretMissing", { name })).join("; ")}.`}
            </SkillBannerFrame>
          );
        }
        return null;
      })}
    </>
  );
}
