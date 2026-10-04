// src/components/skills/SkillRequiresTab.tsx — a skill's Requires tab: what its SKILL.md declares, in four groups.
//
// Canvas 4.3.10 / 4.3.56. Commands (`requires: commands`) — each one's state on
// this machine from the CLIs list (GET /clis, so this tab and the CLIs page can
// never disagree) and "View in CLIs"; Secrets (`requires: secrets`) — set or
// not in Coffer's secret store, names only; Tools (`tools:`) — MCP servers and
// custom-tool groups by name, with a Kind column and Healthy / Off / Failing;
// Skills (`metadata.requires`) — other skills it loads and whether they are
// delivered to the same agents. A group with nothing in it is not drawn. The
// fixes live in the banner above the tabs, never in a row: the commands'
// hand-off is one button there (SkillDependencyBanners), and a missing command
// never stops delivery.
import { Trans, useTranslation } from "react-i18next";
import { RefreshCw, Terminal } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Section } from "@/components/Section";
import { SkillRequireRow } from "@/components/skills/SkillRequireRow";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { Cli } from "@/lib/api/clis";
import type { SkillOut } from "@/lib/api/skills";
import { cliTone, oldestCheck, relativeTime } from "@/lib/clis/format";
import { useCheckClis, useClis } from "@/lib/hooks/useClis";
import { joinNames } from "@/lib/skills/names";
import { toolHref } from "@/lib/skills/toolLinks";
import type { StatusTone } from "@/lib/statusTone";

interface Props {
  skill: SkillOut;
}

const TOOL_TONE: Record<SkillOut["requires_tools"][number]["status"], StatusTone> = {
  healthy: "ok",
  off: "warn",
  failing: "err",
};

function StateWord({ cli }: { cli: Cli | undefined }) {
  const { t } = useTranslation();
  if (!cli) return <StatusWord tone="off">{t("skills.requires.unknown")}</StatusWord>;
  const word =
    cli.status === "ready"
      ? [t("skills.requires.found"), cli.version].filter(Boolean).join(" · ")
      : cli.status === "outdated"
        ? t("skills.requires.outdated", { version: cli.version, min: cli.min_version })
        : t(`skills.requires.state.${cli.status}`);
  return <StatusWord tone={cliTone(cli.status)}>{word}</StatusWord>;
}

/** A group: its title, the one sentence saying where it is declared, the rows. */
function Group({
  title,
  intro,
  actions,
  testId,
  children,
}: {
  title: string;
  intro: React.ReactNode;
  actions?: React.ReactNode;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <Section
      title={title}
      actions={actions}
      gap="tight"
      testId={testId}
      className="mt-8 first:mt-0"
    >
      <p className="text-xs text-text-muted">{intro}</p>
      <ul className="mt-1.5">{children}</ul>
    </Section>
  );
}

export function SkillRequiresTab({ skill }: Props) {
  const { t, i18n } = useTranslation();
  const { data, error } = useClis();
  const check = useCheckClis();
  const byCommand = new Map((data?.items ?? []).map((cli) => [cli.command, cli]));
  const commands = skill.requires.map((req) => ({ req, cli: byCommand.get(req.command) }));
  const checked = oldestCheck(commands.flatMap((r) => (r.cli ? [r.cli] : [])));
  const secrets = skill.requires_secrets ?? [];
  const tools = skill.requires_tools ?? [];
  const skills = skill.requires_skills ?? [];
  const code = <code className="font-mono" />;

  if (commands.length + secrets.length + tools.length + skills.length === 0) {
    return (
      <EmptyState
        icon={Terminal}
        title={t("skills.requires.emptyTitle")}
        description={t("skills.requires.emptyBody")}
      />
    );
  }

  return (
    <div className="flex flex-col">
      {commands.length > 0 ? (
        <Group
          title={t("skills.requires.commandsTitle")}
          testId="skill-requires-commands"
          actions={
            <Button
              variant="ghost"
              size="sm"
              disabled={check.isPending}
              onClick={() => check.mutate()}
            >
              <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
              {check.isPending ? t("clis.checking") : t("clis.checkAgain")}
            </Button>
          }
          intro={
            <>
              <Trans i18nKey="skills.requires.commandsIntro" components={{ code }} />
              {checked
                ? ` ${t("skills.requires.checkedAgo", { when: relativeTime(checked, i18n.language) })}`
                : null}
              {error ? ` ${t("skills.requires.loadFailed")}: ${translateApiError(t, error)}` : null}
            </>
          }
        >
          {commands.map(({ req, cli }) => (
            <SkillRequireRow
              key={req.command}
              name={req.command}
              note={
                req.min_version ? t("skills.requires.needsAtLeast", { min: req.min_version }) : null
              }
              state={<StateWord cli={cli} />}
              to={`/clis/${encodeURIComponent(req.command)}`}
              linkLabel={t("skills.requires.viewInClis")}
            />
          ))}
        </Group>
      ) : null}
      {secrets.length > 0 ? (
        <Group
          title={t("skills.requires.secretsTitle")}
          testId="skill-requires-secrets"
          intro={<Trans i18nKey="skills.requires.secretsIntro" components={{ code }} />}
        >
          {secrets.map((secret) => (
            <SkillRequireRow
              key={secret.name}
              name={secret.name}
              state={
                <StatusWord tone={secret.is_set ? "ok" : "warn"}>
                  {secret.is_set
                    ? t("skills.requires.secretSet")
                    : t("skills.requires.secretMissing", { name: secret.name })}
                </StatusWord>
              }
              to="/secrets"
              linkLabel={t("skills.requires.viewInSecrets")}
            />
          ))}
        </Group>
      ) : null}
      {tools.length > 0 ? (
        <Group
          title={t("skills.requires.toolsTitle")}
          testId="skill-requires-tools"
          intro={<Trans i18nKey="skills.requires.toolsIntro" components={{ code }} />}
        >
          {tools.map((tool) => (
            <SkillRequireRow
              key={tool.uid}
              name={tool.name}
              kind={t(`skills.requires.toolKind.${tool.kind}`)}
              state={
                <StatusWord tone={TOOL_TONE[tool.status]}>
                  {t(`skills.requires.toolState.${tool.status}`)}
                </StatusWord>
              }
              note={tool.status === "healthy" ? null : tool.why}
              to={toolHref(tool)}
              linkLabel={t(`skills.requires.viewInTools.${tool.kind}`)}
            />
          ))}
        </Group>
      ) : null}
      {skills.length > 0 ? (
        <Group
          title={t("skills.requires.skillsTitle")}
          testId="skill-requires-skills"
          intro={<Trans i18nKey="skills.requires.skillsIntro" components={{ code }} />}
        >
          {skills.map((s) => (
            <SkillRequireRow
              key={s.name}
              name={s.name}
              state={
                <StatusWord tone={s.found && s.delivered_to_same_agents ? "ok" : "warn"}>
                  {!s.found
                    ? t("skills.requires.skillMissing")
                    : s.delivered_to_same_agents
                      ? t("skills.requires.skillDelivered")
                      : t("skills.requires.skillNotDelivered", {
                          agents: joinNames(s.missing_agent_names, i18n.language),
                        })}
                </StatusWord>
              }
              to={s.found ? `/skills/${encodeURIComponent(s.name)}` : undefined}
              linkLabel={t("skills.requires.viewInSkills")}
            />
          ))}
        </Group>
      ) : null}
    </div>
  );
}
