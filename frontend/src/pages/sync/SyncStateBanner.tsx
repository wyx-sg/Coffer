// frontend/src/pages/sync/SyncStateBanner.tsx
//
// The Status tab's first line: the page's one state, said in a sentence
// (6.5.01 in sync, 6.5.02 changes to push, 6.5.03 syncing, 6.5.04 changes
// pulled, 6.5.11 rolled back, and a paused remote). A stopped round and a
// problem ask something of the person, so they get their own cards —
// `SyncStopBanner` and `SyncProblemBanner`.
//
// "The other Mac" is named when there is exactly one: "whatever Mac mini
// pushed" is the sentence the boards write; with several peers the sentence
// says "the other Macs" rather than picking one.
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, Check, Pause, RefreshCw, Undo2 } from "lucide-react";

import type { SyncRound, SyncStatus } from "@/lib/api/sync";
import { useMachines } from "@/lib/hooks/useMachines";
import { SyncBannerLine } from "./SyncBanner";
import { SyncProblemBanner } from "./SyncProblemBanner";
import { SyncStopBanner } from "./SyncStopBanner";
import type { SyncState } from "./syncPageState";
import { rolledBackFrom } from "./syncRoundLabel";
import { agoPhrase, clock } from "./syncTime";

/** The one other Mac's name, or null when there are none or several. */
function useSyncPeer(): string | null {
  const { data } = useMachines();
  const others = (data?.machines ?? []).filter((m) => !m.is_self);
  return others.length === 1 ? others[0].name : null;
}

function joinParts(parts: (string | null | false)[]): string {
  return parts.filter(Boolean).join(" · ");
}

function nextRound(t: TFunction, status: SyncStatus): string | null {
  return status.next_round_at
    ? t("sync.banner.nextRoundAt", { time: clock(status.next_round_at) })
    : null;
}

function InSync({ status }: { status: SyncStatus }) {
  const { t } = useTranslation();
  const last = status.last_round;
  const ago = last ? agoPhrase(last.finished_at, t) : null;
  const lastPart = last
    ? t(ago ? "sync.banner.lastRoundAgo" : "sync.banner.lastRound", {
        time: clock(last.finished_at),
        ago,
        pulled: last.pulled_files,
        pushed: last.pushed_files,
      })
    : t("sync.banner.noRoundYet");
  return (
    <SyncBannerLine icon={Check} tone="ok" title={t("sync.banner.inSync")}>
      {joinParts([
        lastPart,
        nextRound(t, status),
        t("sync.banner.machines", { count: status.machines }),
      ])}
    </SyncBannerLine>
  );
}

function Pulled({ status, count }: { status: SyncStatus; count: number }) {
  const { t } = useTranslation();
  const last = status.last_round as SyncRound;
  const from = [...new Set(last.pulled.map((c) => c.machine).filter(Boolean))].join(", ");
  return (
    <SyncBannerLine
      icon={ArrowDown}
      tone="ok"
      title={
        from ? t("sync.banner.pulledFrom", { count, from }) : t("sync.banner.pulled", { count })
      }
    >
      {joinParts([
        t("sync.banner.roundAt", { time: clock(last.finished_at) }),
        last.pushed_files > 0
          ? t("sync.banner.pushedCount", { count: last.pushed_files })
          : t("sync.banner.nothingToPush"),
        nextRound(t, status),
      ])}
    </SyncBannerLine>
  );
}

function ToPush({ status, count }: { status: SyncStatus; count: number }) {
  const { t } = useTranslation();
  const peer = useSyncPeer() ?? t("sync.banner.otherMacs");
  return (
    <SyncBannerLine icon={ArrowUp} tone="info" title={t("sync.banner.toPush", { count })}>
      {status.next_round_at
        ? t("sync.banner.toPushNextAt", { time: clock(status.next_round_at), peer })
        : t("sync.banner.toPushNext", { peer })}
    </SyncBannerLine>
  );
}

function RolledBack({ status, runs }: { status: SyncStatus; runs: SyncRound[] }) {
  const { t } = useTranslation();
  const peer = useSyncPeer() ?? t("sync.banner.otherMacs");
  const last = status.last_round as SyncRound;
  const undone = rolledBackFrom(last, runs);
  return (
    <SyncBannerLine
      icon={Undo2}
      tone="info"
      title={
        undone
          ? t("sync.banner.rolledBack", { time: clock(undone.finished_at) })
          : t("sync.banner.rolledBackTo", { snapshot: last.snapshot ?? "" })
      }
    >
      {status.next_round_at
        ? t("sync.banner.rolledBackNextAt", { time: clock(status.next_round_at), peer })
        : t("sync.banner.rolledBackNext", { peer })}
    </SyncBannerLine>
  );
}

interface Props {
  status: SyncStatus;
  state: SyncState;
  runs: SyncRound[];
  /** When the round this page asked for started, while the daemon has not said yet. */
  startedAt: string | null;
  onRun: () => void;
}

export function SyncStateBanner({ status, state, runs, startedAt, onRun }: Props) {
  const { t } = useTranslation();
  switch (state.kind) {
    case "setup":
      return null;
    case "syncing": {
      const since = status.running_since ?? startedAt;
      return (
        <SyncBannerLine
          icon={RefreshCw}
          tone="info"
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
        <SyncBannerLine icon={Pause} tone="off" title={t("sync.banner.paused")}>
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
      return status.problem ? (
        <SyncProblemBanner status={status} runs={runs} onRun={onRun} running={false} />
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
