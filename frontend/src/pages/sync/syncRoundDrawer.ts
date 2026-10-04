// frontend/src/pages/sync/syncRoundDrawer.ts — the round drawer's title and duration.
import type { TFunction } from "i18next";

import type { SyncRound } from "@/lib/api/sync";
import { clock, dayLabel } from "./syncTime";

export function seconds(from: string, to: string): number {
  const ms = new Date(to).getTime() - new Date(from).getTime();
  return Number.isFinite(ms) ? Math.max(0, Math.round(ms / 100) / 10) : 0;
}

export function drawerTitle(t: TFunction, run: SyncRound): string {
  const day = dayLabel(run.finished_at, t);
  const time = clock(run.finished_at);
  if (day === t("sync.rounds.today")) return t("sync.drawer.titleToday", { time });
  if (day === t("sync.rounds.yesterday")) return t("sync.drawer.titleYesterday", { time });
  return t("sync.drawer.titleDate", { time, date: day });
}
