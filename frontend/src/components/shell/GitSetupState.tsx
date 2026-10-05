// src/components/shell/GitSetupState.tsx — the screen that takes every page's place while the daemon waits for git.
//
// Board 1.1.22 (Daemon · Waiting for git), drawn like the offline state
// (1.1.19) beside it: in the workspace, the sidebar stays. Spec web-ui "Show a
// setup screen while the daemon waits for git": what is wrong (no git, or a
// git older than the vault needs), why Coffer needs it in one sentence, the
// hand-off with the daemon's own prompt, and Check again.
//
// The hand-off is the shared split button. Handing off to an agent needs the
// daemon fully started; in the setup state no managed agent answers, so the
// component falls back to Copy prompt, for the person's agent outside Coffer. Check again asks the daemon to look for git
// again; once it is there the daemon is restarted the way this host restarts
// it and the page carries on into the app (`useCheckGitAgain`).
import { useTranslation } from "react-i18next";
import { Clock, GitBranch, RotateCw } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import type { DaemonSetup } from "@/lib/api/daemon";
import { restartErrorText } from "@/lib/daemonRestart";
import { useCheckGitAgain } from "@/lib/hooks/useDaemon";

/** A check time as the clock reads it ("14:02"). */
function clockTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function GitSetupState({ setup }: { setup: DaemonSetup }) {
  const { t } = useTranslation();
  const check = useCheckGitAgain();
  const problem =
    setup.reason === "git_missing"
      ? t("daemon.setupState.missing")
      : t("daemon.setupState.tooOld", { found: setup.found ?? "", needed: setup.needed });
  const still = check.data && !check.data.ready ? check.data : null;
  const stillLine = still
    ? setup.reason === "git_missing"
      ? t("daemon.setupState.stillMissing", { time: clockTime(still.checkedAt) })
      : t("daemon.setupState.stillTooOld", {
          found: setup.found ?? "",
          time: clockTime(still.checkedAt),
        })
    : null;

  return (
    <div
      className="flex min-h-full flex-1 items-center justify-center p-8"
      data-testid="git-setup"
      data-reason={setup.reason}
      role="alert"
    >
      <div className="flex w-[460px] max-w-full flex-col items-center gap-5 text-center">
        <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <GitBranch className="size-[22px]" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex flex-col gap-1.5">
          <h1 className="text-lg font-bold tracking-tight text-text">
            {t("daemon.setupState.title")}
          </h1>
          <p className="text-sm leading-normal text-text-muted">
            {problem} {t("daemon.setupState.why")}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <AgentHandoff prompt={setup.handoff.prompt} size="lg" help={false} />
          <Button
            size="lg"
            loading={check.isPending}
            onClick={() => check.mutate()}
            data-testid="git-check-again"
          >
            <RotateCw aria-hidden />
            {check.restarting
              ? t("daemon.setupState.restarting")
              : check.isPending
                ? t("daemon.setupState.checking")
                : t("daemon.setupState.checkAgain")}
          </Button>
        </div>
        {check.error ? (
          <p className="text-xs text-danger">{restartErrorText(t, check.error)}</p>
        ) : null}
        {stillLine ? (
          <p className="inline-flex items-center justify-center gap-x-2 text-xs text-text-muted">
            <Clock className="size-[13px] shrink-0" strokeWidth={1.75} aria-hidden />
            {stillLine}
          </p>
        ) : null}
      </div>
    </div>
  );
}
