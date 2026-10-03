// src/components/clis/CliProblemBanner.tsx — what a CLI's problem costs, under its detail header (boards 4.4.05–4.4.08).
//
// Title, a plain sentence naming the MCP servers that can't start and the
// skills that fail at the step calling the command (too old: the minimum it
// needs; not logged in: the login check and when it failed), and the fix in the
// banner: Check again (re-probes this one command), then [Ask an agent ▾] and
// its "?" with the daemon's hand-off prompt — Coffer never installs, updates
// or logs in for the person. A ready command has no banner.
import { CircleAlert, RefreshCw, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import { serverNames } from "@/lib/clis/format";
import { useCheckCli } from "@/lib/hooks/useClis";

function useBody(cli: Cli): string {
  const { t, i18n } = useTranslation();
  const list = new Intl.ListFormat(i18n.language, { style: "long", type: "conjunction" });
  const skills = list.format(cli.needed_by.map((n) => n.skill_name));
  const count = cli.needed_by.length;
  const command = cli.command;
  let reason: string;
  if (cli.status === "outdated") {
    reason = t("clis.banner.outdatedBody", {
      skills,
      command,
      version: cli.min_version ?? "",
      count,
    });
  } else if (count === 0) {
    reason = t("clis.banner.serversBody", { servers: serverNames(cli) });
  } else if (cli.needed_by_servers.length === 0) {
    reason = t("clis.banner.skillsBody", { skills, command, count });
  } else {
    reason = t("clis.banner.bothBody", { servers: serverNames(cli), skills, command, count });
  }
  const check = cli.login.check?.join(" ");
  if (cli.status === "logged_out" && check) {
    const time = new Date(cli.checked_at).toLocaleTimeString(i18n.language, {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    reason += ` ${t("clis.banner.loginFailed", { check, time })}`;
  }
  return `${reason} ${t(`clis.banner.hand.${cli.status}`)}`;
}

export function CliProblemBanner({ cli }: { cli: Cli }) {
  const { t, i18n } = useTranslation();
  const check = useCheckCli(cli.command);
  const body = useBody(cli);
  if (cli.status === "ready") return null;
  const list = new Intl.ListFormat(i18n.language, { style: "long", type: "conjunction" });
  const title = t(`clis.banner.${cli.status}`, {
    command: cli.command,
    found: cli.version ?? "",
    skills: list.format(cli.needed_by.map((n) => n.skill_name)),
    count: cli.needed_by.length,
  });
  const Icon = cli.status === "missing" ? CircleAlert : TriangleAlert;
  return (
    <Alert
      variant={cli.status === "missing" ? "error" : "warning"}
      data-testid="cli-problem"
      className="flex items-start gap-3"
    >
      <Icon aria-hidden />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-label text-text">{title}</p>
        <p className="text-xs leading-[1.45] text-text-muted">{body}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={check.isPending}
          onClick={() => check.mutate()}
        >
          <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
          {check.isPending ? t("clis.checking") : t("clis.checkAgain")}
        </Button>
        {cli.handoff ? <AgentHandoff prompt={cli.handoff.prompt} size="sm" /> : null}
      </div>
    </Alert>
  );
}
