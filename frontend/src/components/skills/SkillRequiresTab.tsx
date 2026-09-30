// src/components/skills/SkillRequiresTab.tsx — a skill's Requires tab: the commands its SKILL.md declares.
//
// Read from the CLIs list (GET /clis), keeping the rows this skill appears in
// under `needed_by`, so the tab and the CLIs page can never disagree. Each
// command links to its page on the CLIs page (spec web-ui "a skill's
// requirement links to its CLI"); Install… / Copy command are shortcuts to the
// same confirmation and copy the CLI page offers. A missing command never stops
// delivery — the footnote says so.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { CliActionButton } from "@/components/clis/CliActionButton";
import { CliInstallDialog } from "@/components/clis/CliInstallDialog";
import { ClisWarnings } from "@/components/clis/ClisWarnings";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliTone, oldestCheck, relativeTime } from "@/lib/clis/format";
import { useCheckClis, useClis } from "@/lib/hooks/useClis";

interface Props {
  skillUid: string;
}

function RequirementLine({ cli, skillUid }: { cli: Cli; skillUid: string }) {
  const { t } = useTranslation();
  const why = cli.needed_by.find((n) => n.skill_uid === skillUid)?.why;
  switch (cli.status) {
    case "ready":
      return (
        <>
          {t("skills.requires.readyLine", {
            command: cli.command,
            version: cli.version ?? "",
            path: cli.path ?? "",
          })}
        </>
      );
    case "missing":
      return <>{[t("skills.requires.notOnPath"), why].filter(Boolean).join(" ")}</>;
    case "outdated":
      return (
        <>
          {[t("skills.requires.outdatedLine", { version: cli.version, min: cli.min_version }), why]
            .filter(Boolean)
            .join(" ")}
        </>
      );
    case "logged_out":
      return (
        <>
          {t("skills.requires.loggedOutBefore")}{" "}
          <code className="font-mono text-text">{cli.login.command}</code>{" "}
          {t("skills.requires.loggedOutAfter")}
        </>
      );
  }
}

export function SkillRequiresTab({ skillUid }: Props) {
  const { t, i18n } = useTranslation();
  const { data, isPending, error } = useClis();
  const check = useCheckClis();
  const [installFor, setInstallFor] = useState<Cli | null>(null);

  if (isPending) return <p className="text-sm text-text-muted">{t("common.loading")}</p>;
  if (error) {
    return (
      <EmptyState
        tone="error"
        title={t("skills.requires.loadFailed")}
        description={translateApiError(t, error)}
      />
    );
  }

  const rows = data.items.filter((cli) => cli.needed_by.some((n) => n.skill_uid === skillUid));
  const warnings = data.warnings.filter((w) => w.skill_uid === skillUid);
  const missing = rows.filter((cli) => cli.status === "missing").map((cli) => cli.command);
  const checked = oldestCheck(rows);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-label">{t("skills.requires.title")}</h2>
        <span className="text-xs text-text-muted">
          {[
            t("skills.requires.declared"),
            checked ? t("clis.checkedAgo", { when: relativeTime(checked, i18n.language) }) : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
        <div className="ml-auto flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={check.isPending}
            onClick={() => check.mutate()}
          >
            <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
            {check.isPending ? t("clis.checking") : t("clis.checkAgain")}
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/clis">{t("skills.requires.openClis")}</Link>
          </Button>
        </div>
      </div>

      <ClisWarnings warnings={warnings} />

      {rows.length === 0 ? (
        <EmptyState
          title={t("skills.requires.empty")}
          description={t("skills.requires.emptyHint")}
        />
      ) : (
        <ul
          className="paper-card divide-y divide-border-subtle"
          aria-label={t("skills.requires.title")}
        >
          {rows.map((cli) => (
            <li key={cli.command} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
              <Link
                to={`/clis/${encodeURIComponent(cli.command)}`}
                className="w-28 shrink-0 font-mono text-sm font-label text-accent-text hover:underline"
              >
                {cli.command}
              </Link>
              <StatusWord tone={cliTone(cli.status)} className="w-28">
                {t(`clis.status.${cli.status}`)}
              </StatusWord>
              <span className="min-w-0 flex-1 text-xs text-text-muted">
                <RequirementLine cli={cli} skillUid={skillUid} />
              </span>
              <CliActionButton
                cli={cli}
                onInstall={setInstallFor}
                copyLabel={t("clis.actions.copyCommand")}
              />
            </li>
          ))}
        </ul>
      )}

      {missing.length > 0 ? (
        <p className="text-xs text-text-muted">
          {t("skills.requires.footnote", { commands: missing.join(", ") })}
        </p>
      ) : null}

      <CliInstallDialog cli={installFor} onOpenChange={(open) => !open && setInstallFor(null)} />
    </div>
  );
}
