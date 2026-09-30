// src/components/clis/CliProblemBanner.tsx — what a CLI's problem costs, over its detail page, with the remedy beside it.
//
// Missing and too old name the skills that fail at the step calling the
// command and offer Install… / Update… (the confirmation, never a run); not
// logged in adds the login command to run in a terminal and offers to copy it.
// A ready command has no banner.
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { Cli } from "@/lib/api/clis";
import { skillNames } from "@/lib/clis/format";
import { CliActionButton } from "./CliActionButton";

interface Props {
  cli: Cli;
  onInstall: (cli: Cli) => void;
}

export function CliProblemBanner({ cli, onInstall }: Props) {
  const { t } = useTranslation();
  if (cli.status === "ready") return null;
  const count = cli.needed_by.length;
  const title = t(`clis.banner.${cli.status}`, {
    command: cli.command,
    version: cli.min_version ?? "",
    count,
  });
  return (
    <Alert variant={cli.status === "missing" ? "error" : "warning"} data-testid="cli-problem">
      <TriangleAlert aria-hidden />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>
            {t("clis.banner.body", { skills: skillNames(cli), command: cli.command })}
            {cli.status === "logged_out" && cli.login.command ? (
              <>
                {" "}
                {t("clis.banner.loginBefore")}{" "}
                <code className="font-mono text-text">{cli.login.command}</code>{" "}
                {t("clis.banner.loginAfter")}
              </>
            ) : null}
          </AlertDescription>
        </div>
        <CliActionButton
          cli={cli}
          onInstall={onInstall}
          copyLabel={t("clis.actions.copyCommand")}
        />
      </div>
    </Alert>
  );
}
