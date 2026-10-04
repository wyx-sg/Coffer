// frontend/src/pages/sync/SyncStateBanner.tsx
//
// The Status tab's first line: the page's one state, said in a sentence
// (6.4.01 in sync, 6.4.02 changes to push, 6.4.03 syncing, 6.4.04 changes
// pulled, 6.4.13 rolled back, and a paused remote), with the one grey areas
// line under it. A stopped round and a problem ask something of the person,
// so they get their own cards — `SyncStopBanner` and `SyncProblemBanner` — and
// no areas line; a problem the person ignored shows nothing here.
import { useTranslation } from "react-i18next";
import { Pause, RefreshCw } from "lucide-react";

import type { SyncRound, SyncStatus } from "@/lib/api/sync";
import { SyncAreasLine } from "./SyncAreasLine";
import { SyncBannerLine } from "./SyncBanner";
import { SyncProblemBanner } from "./SyncProblemBanner";
import { SyncStopBanner } from "./SyncStopBanner";
import type { SyncState } from "./syncPageState";
import { InSync, Pulled, RolledBack, ToPush } from "./SyncStateLines";
import { clock } from "./syncTime";
import { PROBLEM_REASON, useSyncIgnore } from "./useSyncIgnore";

interface Props {
  status: SyncStatus;
  state: SyncState;
  runs: SyncRound[];
  /** When the round this page asked for started, while the daemon has not said yet. */
  startedAt: string | null;
  /** Git missing's Check again: read the status once more. */
  onRecheck: () => void;
  rechecking: boolean;
}

export function SyncStateBanner({ status, state, runs, startedAt, onRecheck, rechecking }: Props) {
  const { t } = useTranslation();
  const { isIgnored } = useSyncIgnore();
  switch (state.kind) {
    case "setup":
      return null;
    case "syncing": {
      const since = status.running_since ?? startedAt;
      return (
        <SyncBannerLine
          icon={RefreshCw}
          tone="info"
          footnote={<SyncAreasLine areas={status.areas} />}
          title={
            since ? t("sync.banner.startedAt", { time: clock(since) }) : t("sync.banner.started")
          }
        >
          {t("sync.banner.runningHint")}
        </SyncBannerLine>
      );
    }
    case "paused":
      return (
        <SyncBannerLine
          icon={Pause}
          tone="off"
          title={t("sync.banner.paused")}
          footnote={<SyncAreasLine areas={status.areas} />}
        >
          {t("sync.banner.pausedHint")}
        </SyncBannerLine>
      );
    case "conflicts":
    case "held":
      return <SyncStopBanner kind={state.kind} count={state.count} />;
    case "push_failed":
    case "plaintext_found":
    case "unreachable":
    case "auth_failed":
    case "waiting_approval":
    case "cloud_folder":
    case "git_missing":
    case "layout":
    case "failed":
      return status.problem && !isIgnored(PROBLEM_REASON[status.problem.kind] ?? "") ? (
        <SyncProblemBanner
          status={status}
          runs={runs}
          onRecheck={onRecheck}
          rechecking={rechecking}
        />
      ) : null;
    default:
      break;
  }
  // Nothing wrong: what the last round did, unless it was a rollback, which
  // is the thing a person who just pressed Roll back is looking for.
  if (status.last_round?.status === "rolled_back")
    return <RolledBack status={status} runs={runs} />;
  if (state.kind === "to_push") return <ToPush status={status} count={state.count} />;
  if (state.kind === "pulled") return <Pulled status={status} count={state.count} />;
  return <InSync status={status} />;
}
