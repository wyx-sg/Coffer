// frontend/src/pages/sync/SyncProblemBanner.tsx
//
// Why sync is not working right now, as a card that says what to do about it
// (6.4.14 push rejected, 6.4.15 remote unreachable, 6.4.16 sign-in failed,
// 6.4.17 git missing, 6.4.18 cloud folder, 6.4.32 plaintext secret, 6.4.33
// push token waiting).
//
// Each card is a plain sentence first. Git's own words matter for a rejected
// push — the branch rule it names is the fix — so they are shown in full; for
// an unreachable remote or a refused sign-in they are one click away under
// "Show git's message", because the sentence already says what happened. The
// daemon scrubbed any token out of them before storing them.
//
// There is no Retry in a card: the header's Sync now is the one way to run a
// round (principle 20). Chores that depend on this machine (a network, a
// missing git) are handed to an agent with the backend's own prompt
// (`problem.handoff`); the page never spells out commands. Every card's ×
// is Ignore (principle 19) and the card stays hidden while it is ignored.
import { useTranslation } from "react-i18next";
import { AlertTriangle, WifiOff, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SyncRound, SyncStatus } from "@/lib/api/sync";
import { SyncBannerCard } from "./SyncBanner";
import { Actions, Body, GitMessage, GitMessageDisclosure, Handoff } from "./SyncProblemParts";
import { lastGoodRound } from "./syncProblemRounds";
import { SyncCloudFolderCard } from "./SyncCloudFolderCard";
import { SyncPlaintextCard } from "./SyncPlaintextCard";
import { AuthFailedCard, WaitingApprovalCard } from "./SyncSignInCards";
import { waitingCount } from "./syncPageState";
import { clock, remoteHost } from "./syncTime";
import { PROBLEM_REASON, useSyncIgnore } from "./useSyncIgnore";

interface Props {
  status: SyncStatus;
  runs: SyncRound[];
  /** Re-read the status — git missing's Check again. */
  onRecheck: () => void;
  rechecking: boolean;
}

export function SyncProblemBanner({ status, runs, onRecheck, rechecking }: Props) {
  const { t } = useTranslation();
  const { ignorer } = useSyncIgnore();
  const problem = status.problem;
  if (!problem) return null;
  const host = status.remote ? remoteHost(status.remote.url) : t("sync.problem.theRemote");
  const waiting = waitingCount(status);
  const reason = PROBLEM_REASON[problem.kind];
  const onIgnore = reason ? ignorer(reason) : undefined;

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
          onIgnore={onIgnore}
          testId="sync-problem"
        >
          <Body>
            {pulled > 0
              ? t("sync.problem.push_failed.bodyPulled", { pulled, count: waiting })
              : t("sync.problem.push_failed.body", { count: waiting })}
          </Body>
          {problem.message ? <GitMessage message={problem.message} /> : null}
          <Actions>
            <Handoff problem={problem} />
          </Actions>
        </SyncBannerCard>
      );
    }
    case "plaintext_found":
      return <SyncPlaintextCard problem={problem} onIgnore={onIgnore} />;
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
          onIgnore={onIgnore}
          testId="sync-problem"
        >
          <Body>{parts.filter(Boolean).join(" ")}</Body>
          <GitMessageDisclosure message={problem.message} />
          <Actions>
            <Handoff problem={problem} />
          </Actions>
        </SyncBannerCard>
      );
    }
    case "auth_failed":
      return <AuthFailedCard problem={problem} host={host} onIgnore={onIgnore} />;
    case "waiting_approval":
      return <WaitingApprovalCard problem={problem} host={host} onIgnore={onIgnore} />;
    case "cloud_folder":
      return <SyncCloudFolderCard status={status} onIgnore={onIgnore} />;
    case "git_missing":
      return (
        <SyncBannerCard
          icon={Wrench}
          tone="err"
          title={t("sync.problem.git_missing.title")}
          onIgnore={onIgnore}
          testId="sync-problem"
        >
          <Body>
            {waiting > 0
              ? t("sync.problem.git_missing.bodyWaiting", { count: waiting })
              : t("sync.problem.git_missing.body")}
          </Body>
          <GitMessageDisclosure message={problem.message} />
          <Actions>
            <Handoff problem={problem} />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onRecheck}
              loading={rechecking}
            >
              {t("sync.problem.checkAgain")}
            </Button>
          </Actions>
        </SyncBannerCard>
      );
    default:
      return (
        <SyncBannerCard
          icon={AlertTriangle}
          tone="err"
          title={t(`sync.problem.${problem.kind}.title`)}
          onIgnore={onIgnore}
          testId="sync-problem"
        >
          <Body>{t(`sync.problem.${problem.kind}.body`)}</Body>
          {problem.message ? <GitMessage message={problem.message} /> : null}
          <Actions>
            <Handoff problem={problem} />
          </Actions>
        </SyncBannerCard>
      );
  }
}
