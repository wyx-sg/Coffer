// src/components/skills/SkillRequiresTab.tsx — a skill's Requires tab: the commands its SKILL.md declares.
//
// Canvas 4.3.07: one row per command — its name, its state on this machine
// (from the CLIs list, GET /clis, so the tab and the CLIs page can never
// disagree) and Open in CLIs. A command that needs the person also offers the
// same hand-off to an agent (AgentHandoff) its CLI page does — Coffer never
// installs or logs in itself (Principle IV). A missing command
// never stops delivery — the footnote says so.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, RefreshCw, Terminal } from "lucide-react";

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

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={Terminal}
        title={t("skills.requires.emptyTitle")}
        description={t("skills.requires.emptyBody")}
      />
    );
  }

  return (
    <section className="flex flex-col" aria-label={t("skills.requires.title")}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle pb-2">
        <h3 className="text-sm font-semibold">{t("skills.requires.title")}</h3>
        <span className="text-xs text-text-muted">{t("skills.requires.declared")}</span>
        <span className="ml-auto flex items-center gap-2">
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
      </div>

      {error ? (
        <p className="pt-2 text-xs text-danger">
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

      <p className="pt-3 text-xs text-text-muted">{t("skills.requires.footnote")}</p>
    </section>
  );
}
