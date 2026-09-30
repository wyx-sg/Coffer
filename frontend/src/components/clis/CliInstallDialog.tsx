// src/components/clis/CliInstallDialog.tsx — the confirmation before Coffer runs Homebrew, then the run itself.
//
// Nothing runs until the person presses "Run <command>": the dialog first names
// the exact command (the daemon's `install_command`), the installer, why the
// skills want it, and where the output goes. Confirming POSTs the declared
// formula — the daemon refuses any other — and the dialog turns into the job's
// output, polled until it ends. Homebrew is the only installer anywhere in the
// app. A failure to start stays inline and the dialog stays open.
import { useEffect } from "react";
import { AlertCircle, Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { skillNames } from "@/lib/clis/format";
import { useCliInstall } from "@/lib/hooks/useClis";
import { useCopyText } from "@/lib/hooks/useCopyText";
import { CliInstallOutput } from "./CliInstallOutput";

interface Props {
  /** The command to install; the dialog is closed while it is null. */
  cli: Cli | null;
  onOpenChange: (open: boolean) => void;
}

export function CliInstallDialog({ cli, onOpenChange }: Props) {
  return (
    <Dialog open={cli !== null} onOpenChange={onOpenChange}>
      {cli ? <InstallBody key={cli.command} cli={cli} onClose={() => onOpenChange(false)} /> : null}
    </Dialog>
  );
}

function InstallBody({ cli, onClose }: { cli: Cli; onClose: () => void }) {
  const { t } = useTranslation();
  const run = useCliInstall(cli.command);
  const { copied, copy } = useCopyText();
  const command = cli.install_command ?? "";
  const { attach } = run;

  // Opened while a job already runs: follow it rather than offer a second one.
  useEffect(() => {
    if (cli.install_state === "running") attach();
    // Once, on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const started = run.job !== null;
  const title = !started
    ? t(cli.status === "outdated" ? "clis.install.titleUpdate" : "clis.install.titleInstall", {
        command: cli.command,
      })
    : run.job?.state === "running"
      ? t("clis.install.titleRunning", { command })
      : run.job?.state === "succeeded"
        ? t("clis.install.titleSucceeded", { command })
        : t("clis.install.titleFailed", { command });

  const count = cli.needed_by.length;
  const why = cli.min_version
    ? t("clis.install.whyWithMin", {
        count,
        command: cli.command,
        version: cli.min_version,
        skills: skillNames(cli),
      })
    : t("clis.install.whyPlain", { count, command: cli.command, skills: skillNames(cli) });

  return (
    <DialogContent className="max-w-[520px]">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {!started ? <DialogDescription>{t("clis.install.intro")}</DialogDescription> : null}
      </DialogHeader>

      {started ? (
        <CliInstallOutput job={run.job} lines={run.lines} />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2 rounded-md border border-border-subtle bg-surface-sunken px-3 py-2">
            <code
              className="min-w-0 flex-1 truncate font-mono text-sm"
              data-testid="cli-install-command"
            >
              {command}
            </code>
            <Button type="button" variant="ghost" size="sm" onClick={() => copy(command)}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              {copied ? t("clis.actions.copied") : t("clis.actions.copy")}
            </Button>
          </div>
          <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-1.5 text-xs">
            <dt className="text-text-muted">{t("clis.install.installer")}</dt>
            <dd>{t("clis.install.homebrew")}</dd>
            <dt className="text-text-muted">{t("clis.install.why")}</dt>
            <dd>{why}</dd>
            <dt className="text-text-muted">{t("clis.install.output")}</dt>
            <dd>{t("clis.install.outputWhere")}</dd>
          </dl>
          <p className="text-xs text-text-muted">{t("clis.install.never")}</p>
        </div>
      )}

      {run.error ? (
        <div className="flex items-start gap-2 text-sm text-danger" role="alert">
          <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
          <span>{translateApiError(t, run.error)}</span>
        </div>
      ) : null}

      <DialogFooter>
        {started ? (
          <Button variant="outline" onClick={onClose}>
            {t("clis.install.close")}
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button
              disabled={run.starting || cli.brew === null}
              onClick={() => {
                if (cli.brew !== null) run.start(cli.brew);
              }}
            >
              {t("clis.install.run", { command })}
            </Button>
          </>
        )}
      </DialogFooter>
    </DialogContent>
  );
}
