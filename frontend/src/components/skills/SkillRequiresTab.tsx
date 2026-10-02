// src/components/skills/SkillRequiresTab.tsx — a skill's Requires tab: the commands its SKILL.md declares.
//
// Canvas 4.3.07: one row per command — its name, its state on this machine
// (from the CLIs list, GET /clis, so the tab and the CLIs page can never
// disagree) and Open in CLIs. A command that needs the person also offers the
// same hand-off to an agent (AgentHandoff) its CLI page does — Coffer never
// installs or logs in itself (Principle IV). A missing command
// never stops delivery — the footnote says so. Below them, the Coffer secrets
// it declares, each set or not set in the secret store; a missing one opens
// the Secrets page, where the person sets it.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, RefreshCw, Terminal } from "lucide-react";

import { Section, SectionStack } from "@/components/Section";
import { EmptyState } from "@/components/EmptyState";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import type { SkillOut } from "@/lib/api/skills";
import { translateApiError } from "@/lib/api/errors";
import { cliTone, oldestCheck, relativeTime } from "@/lib/clis/format";
import { useCheckClis, useClis } from "@/lib/hooks/useClis";

interface Props {
  skill: SkillOut;
}

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

export function SkillRequiresTab({ skill }: Props) {
  const { t, i18n } = useTranslation();
  const { data, error } = useClis();
  const check = useCheckClis();

  // What the skill declares, in its order (spec skill-manager "Show the
  // commands a skill declares it needs"); each one's state on this machine
  // comes from the CLIs list when it has answered.
  const byCommand = new Map((data?.items ?? []).map((cli) => [cli.command, cli]));
  const rows = skill.requires.map((req) => ({ req, cli: byCommand.get(req.command) }));
  const checked = oldestCheck(rows.flatMap((r) => (r.cli ? [r.cli] : [])));
  // The Coffer secrets it declares (spec skill-manager "Declare the secrets a
  // skill requires"), each already answered set / not set by the read model.
  const secrets = skill.requires_secrets ?? [];

  if (rows.length === 0 && secrets.length === 0) {
    return (
      <EmptyState
        icon={Terminal}
        title={t("skills.requires.emptyTitle")}
        description={t("skills.requires.emptyBody")}
      />
    );
  }

  return (
    <SectionStack>
      {rows.length > 0 ? (
        <Section
          title={t("skills.requires.commandsTitle")}
          gap="snug"
          labelled
          help={`${t("skills.requires.declared")}. ${t("skills.requires.footnote")}`}
          actions={
            <span className="flex items-center gap-2">
              {checked ? (
                <span className="text-xs text-text-muted">
                  {t("clis.checkedAgo", { when: relativeTime(checked, i18n.language) })}
                </span>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                disabled={check.isPending}
                onClick={() => check.mutate()}
              >
                <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
                {check.isPending ? t("clis.checking") : t("clis.checkAgain")}
              </Button>
              <Link to="/clis" className="text-xs font-label text-accent-text hover:underline">
                {t("skills.requires.openClis")}
              </Link>
            </span>
          }
        >
          {error ? (
            <p className="text-xs text-danger">
              {t("skills.requires.loadFailed")}: {translateApiError(t, error)}
            </p>
          ) : null}
          <ul className="divide-y divide-border-subtle">
            {rows.map(({ req, cli }) => {
              const href = `/clis/${encodeURIComponent(req.command)}`;
              return (
                <li
                  key={req.command}
                  className="grid grid-cols-[8.5rem_minmax(0,1fr)_auto_auto] items-center gap-4 py-3"
                >
                  <Link
                    to={href}
                    className="truncate font-mono text-sm font-label text-accent-text hover:underline"
                  >
                    {req.command}
                  </Link>
                  <StateWord cli={cli} />
                  {cli?.handoff ? <AgentHandoff prompt={cli.handoff.prompt} size="sm" /> : <span />}
                  <Link
                    to={href}
                    className="inline-flex items-center gap-1 text-xs font-label text-accent-text hover:underline"
                  >
                    {t("skills.requires.openInClis")}
                    <ArrowRight className="size-3" aria-hidden />
                  </Link>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : null}
      {secrets.length > 0 ? <SecretRows secrets={secrets} /> : null}
    </SectionStack>
  );
}

/** One row per declared secret: its name and whether it is set. A secret that
 *  is not set says so and opens the Secrets page, where the person sets it —
 *  no hand-off, and never a value (Principle IV: a person's task). */
function SecretRows({ secrets }: { secrets: SkillOut["requires_secrets"] }) {
  const { t } = useTranslation();
  return (
    <Section
      title={t("skills.requires.secretsTitle")}
      help={t("skills.requires.secretsFootnote")}
      gap="snug"
      testId="skill-requires-secrets"
    >
      <ul className="divide-y divide-border-subtle">
        {secrets.map((secret) => (
          <li
            key={secret.name}
            className="grid grid-cols-[8.5rem_minmax(0,1fr)_auto] items-center gap-4 py-3"
          >
            <span className="truncate font-mono text-sm font-label">{secret.name}</span>
            <StatusWord tone={secret.is_set ? "ok" : "warn"}>
              {secret.is_set
                ? t("skills.requires.secretSet")
                : t("skills.requires.secretMissing", { name: secret.name })}
            </StatusWord>
            {secret.is_set ? (
              <span />
            ) : (
              <Link
                to="/secrets"
                className="inline-flex items-center gap-1 text-xs font-label text-accent-text hover:underline"
              >
                {t("skills.requires.openSecrets")}
                <ArrowRight className="size-3" aria-hidden />
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}
