// src/components/clis/CliProblemBanner.tsx — what a CLI's problem costs, under its detail header.
//
// Missing names the skills that fail at the step calling the command; too old
// names the version found and the minimum the skills need; not logged in shows
// the login command to run in a terminal. The banner carries no button: the
// remedy (the hand-off to an agent) sits in the pane's header. A ready command
// has no banner.
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { Cli } from "@/lib/api/clis";
import { skillNames } from "@/lib/clis/format";

interface Props {
  cli: Cli;
}

function Body({ cli }: Props) {
  const { t } = useTranslation();
  const count = cli.needed_by.length;
  if (cli.status === "outdated") {
    return (
      <>
        {t("clis.banner.outdatedBody", {
          command: cli.command,
          version: cli.min_version ?? "",
          count,
        })}
      </>
    );
  }
  return (
    <>
      {t("clis.banner.body", { skills: skillNames(cli), command: cli.command })}
      {cli.status === "logged_out" && cli.login.command ? (
        <>
          {" "}
          {t("clis.banner.loginBefore")}{" "}
          <code className="font-mono text-text">{cli.login.command}</code>{" "}
          {t("clis.banner.loginAfter")}
        </>
      ) : null}
    </>
  );
}

export function CliProblemBanner({ cli }: Props) {
  const { t } = useTranslation();
  if (cli.status === "ready") return null;
  const title = t(`clis.banner.${cli.status}`, {
    command: cli.command,
    found: cli.version ?? "",
    skills: skillNames(cli),
    count: cli.needed_by.length,
  });
  return (
    <Alert variant={cli.status === "missing" ? "error" : "warning"} data-testid="cli-problem">
      <TriangleAlert aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>
          <Body cli={cli} />
        </AlertDescription>
      </div>
    </Alert>
  );
}
