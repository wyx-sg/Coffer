// frontend/src/pages/sync/SyncProblemBanner.tsx
//
// Why sync is not working right now, as a card that says what to do about it
// (6.5.12 push rejected, 6.5.13 remote unreachable, 6.5.14 sign-in failed,
// 6.5.15 cloud folder, and git missing from this Mac).
//
// Each card is a plain sentence first. Git's own words matter for a rejected
// push — the branch rule it names is the fix — so they are shown in full; for
// an unreachable remote or a refused sign-in they are one click away under
// "Show git's message", because the sentence already says what happened. The
// daemon scrubbed any token out of them before storing them.
//
// Chores that depend on this machine (installing git, fixing a network, a key)
// are handed to an agent with the backend's own prompt (`problem.handoff`);
// the page never spells out commands.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle, KeyRound, RotateCw, Settings2, WifiOff, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SyncRound, SyncStatus } from "@/lib/api/sync";
import { SyncBannerCard } from "./SyncBanner";
import { Body, GitMessage, GitMessageDisclosure, Handoff } from "./SyncProblemParts";
import { lastGoodRound } from "./syncProblemRounds";
import { SyncCloudFolderCard } from "./SyncCloudFolderCard";
import { waitingCount } from "./syncPageState";
import { clock, remoteHost } from "./syncTime";

interface Props {
  status: SyncStatus;
  runs: SyncRound[];
  /** Run a round now — the push card's Retry. */
  onRun: () => void;
  running: boolean;
}

export function SyncProblemBanner({ status, runs, onRun, running }: Props) {
  const { t } = useTranslation();
  const problem = status.problem;
  if (!problem) return null;
  const host = status.remote ? remoteHost(status.remote.url) : t("sync.problem.theRemote");
  const waiting = waitingCount(status);

  switch (problem.kind) {
    case "push_failed": {
      const pulled = status.last_round?.pulled_files ?? 0;
      return (
        <SyncBannerCard
          icon={AlertTriangle}
          tone="err"
          title={t(
            pulled > 0 ? "sync.problem.push_failed.titlePulled" : "sync.problem.push_failed.title",
          )}
          testId="sync-problem"
        >
          <Body>
            {pulled > 0
              ? t("sync.problem.push_failed.bodyPulled", { pulled, count: waiting })
              : t("sync.problem.push_failed.body", { count: waiting })}
          </Body>
          {problem.message ? <GitMessage message={problem.message} /> : null}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onRun} loading={running}>
              <RotateCw aria-hidden />
              {t("sync.problem.retry")}
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/sync?tab=remote">
                <Settings2 aria-hidden />
                {t("sync.problem.openRemote")}
              </Link>
            </Button>
            <Handoff problem={problem} />
          </div>
        </SyncBannerCard>
      );
    }
    case "unreachable": {
      const good = lastGoodRound(runs);
      const parts = [
        good ? t("sync.problem.unreachable.since", { time: clock(good.finished_at) }) : null,
        waiting > 0
          ? t("sync.problem.unreachable.keepsWorkingWaiting", { count: waiting })
          : t("sync.problem.unreachable.keepsWorking"),
        t("sync.problem.unreachable.retry"),
      ];
      return (
        <SyncBannerCard
          icon={WifiOff}
          tone="warn"
          title={t("sync.problem.unreachable.title", { host })}
          testId="sync-problem"
        >
          <Body>{parts.filter(Boolean).join(" ")}</Body>
          <GitMessageDisclosure message={problem.message} />
          <div>
            <Handoff problem={problem} />
          </div>
        </SyncBannerCard>
      );
    }
    case "auth_failed":
      return (
        <SyncBannerCard
          icon={KeyRound}
          tone="err"
          title={t("sync.problem.auth_failed.title")}
          testId="sync-problem"
        >
          <Body>
            {problem.secret_ref ? (
              <>
                <code className="rounded-xs bg-code px-1 py-0.5 font-mono text-xs text-text">
                  {problem.secret_ref}
                </code>{" "}
                {t("sync.problem.auth_failed.body", { host })}
              </>
            ) : (
              t("sync.problem.auth_failed.bodyNoSecret", { host })
            )}
          </Body>
          <GitMessageDisclosure message={problem.message} />
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/sync?tab=remote&focus=secret">{t("sync.problem.chooseSecret")}</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/secrets">{t("sync.problem.openSecrets")}</Link>
            </Button>
            <Handoff problem={problem} />
          </div>
        </SyncBannerCard>
      );
    case "cloud_folder":
      return <SyncCloudFolderCard status={status} />;
    case "git_missing":
      return (
        <SyncBannerCard
          icon={Wrench}
          tone="err"
          title={t("sync.problem.git_missing.title")}
          testId="sync-problem"
        >
          <Body>{t("sync.problem.git_missing.body")}</Body>
          <GitMessageDisclosure message={problem.message} />
          <div>
            <Handoff problem={problem} />
          </div>
        </SyncBannerCard>
      );
    default:
      return (
        <SyncBannerCard
          icon={AlertTriangle}
          tone="err"
          title={t(`sync.problem.${problem.kind}.title`)}
          testId="sync-problem"
        >
          <Body>{t(`sync.problem.${problem.kind}.body`)}</Body>
          {problem.message ? <GitMessage message={problem.message} /> : null}
          <div>
            <Handoff problem={problem} />
          </div>
        </SyncBannerCard>
      );
  }
}
