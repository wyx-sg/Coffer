// frontend/src/pages/sync/SyncStateLines.tsx — the quiet states of the Status tab's
// first line (6.4.01 in sync, 6.4.02 changes to push, 6.4.04 changes pulled,
// 6.4.13 rolled back), each a `SyncBannerLine` with the areas line under it.
//
// "The other Mac" is named when there is exactly one: "whatever Mac mini
// pushed" is the sentence the boards write; with several peers the sentence
// says "the other Macs" rather than picking one.
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, Check, Undo2 } from "lucide-react";

import type { SyncRound, SyncStatus } from "@/lib/api/sync";
import { useMachines } from "@/lib/hooks/useMachines";
import { SyncAreasLine } from "./SyncAreasLine";
import { SyncBannerLine } from "./SyncBanner";
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

export function InSync({ status }: { status: SyncStatus }) {
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
    <SyncBannerLine
      icon={Check}
      tone="ok"
      title={t("sync.banner.inSync")}
      footnote={<SyncAreasLine areas={status.areas} />}
    >
      {joinParts([
        lastPart,
        nextRound(t, status),
        t("sync.banner.machines", { count: status.machines }),
      ])}
    </SyncBannerLine>
  );
}

export function Pulled({ status, count }: { status: SyncStatus; count: number }) {
  const { t } = useTranslation();
  const last = status.last_round as SyncRound;
  const from = [...new Set(last.pulled.map((c) => c.machine).filter(Boolean))].join(", ");
  return (
    <SyncBannerLine
      icon={ArrowDown}
      tone="ok"
      footnote={<SyncAreasLine areas={status.areas} />}
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

export function ToPush({ status, count }: { status: SyncStatus; count: number }) {
  const { t } = useTranslation();
  const peer = useSyncPeer() ?? t("sync.banner.otherMacs");
  return (
    <SyncBannerLine
      icon={ArrowUp}
      tone="info"
      title={t("sync.banner.toPush", { count })}
      footnote={<SyncAreasLine areas={status.areas} />}
    >
      {status.next_round_at
        ? t("sync.banner.toPushNextAt", { time: clock(status.next_round_at), peer })
        : t("sync.banner.toPushNext", { peer })}
    </SyncBannerLine>
  );
}

export function RolledBack({ status, runs }: { status: SyncStatus; runs: SyncRound[] }) {
  const { t } = useTranslation();
  const peer = useSyncPeer() ?? t("sync.banner.otherMacs");
  const last = status.last_round as SyncRound;
  const undone = rolledBackFrom(last, runs);
  return (
    <SyncBannerLine
      icon={Undo2}
      tone="info"
      footnote={<SyncAreasLine areas={status.areas} />}
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
