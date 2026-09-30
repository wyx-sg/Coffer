// src/components/clis/CliProblemBanner.tsx — what a CLI's problem costs, under its detail header.
//
// A plain sentence, nothing to run: missing and not logged in name the MCP
// servers that can't start and the skills that fail at the step calling the
// command; too old names the version found and the minimum the skills need.
// The banner carries no button and no command — the remedy (the daemon's
// hand-off prompt for an agent) sits in the pane's header, because Coffer
// never installs, updates or logs in for the person. A ready command has no
// banner.
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { Cli } from "@/lib/api/clis";
import { neededByCount, serverNames, skillNames } from "@/lib/clis/format";

interface Props {
  cli: Cli;
}

function useBody(cli: Cli): string {
  const { t } = useTranslation();
  const skills = cli.needed_by.length;
  if (cli.status === "outdated") {
    return t("clis.banner.outdatedBody", {
      command: cli.command,
      version: cli.min_version ?? "",
      count: skills,
    });
  }
  const names = { servers: serverNames(cli), skills: skillNames(cli), command: cli.command };
  if (cli.needed_by_servers.length === 0) return t("clis.banner.body", names);
  if (skills === 0) return t("clis.banner.serversBody", names);
  return t("clis.banner.bothBody", { ...names, count: skills });
}

export function CliProblemBanner({ cli }: Props) {
  const { t } = useTranslation();
  const body = useBody(cli);
  if (cli.status === "ready") return null;
  const title = t(`clis.banner.${cli.status}`, {
    command: cli.command,
    found: cli.version ?? "",
    skills: skillNames(cli),
    count: cli.needed_by.length,
    needed: neededByCount(t, cli),
  });
  return (
    <Alert variant={cli.status === "missing" ? "error" : "warning"} data-testid="cli-problem">
      <TriangleAlert aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>{body}</AlertDescription>
      </div>
    </Alert>
  );
}
