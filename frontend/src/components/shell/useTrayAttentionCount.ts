// src/components/shell/useTrayAttentionCount.ts — keep the tray's count in step with the attention list.
//
// The menu bar's count is the length of the Overview's attention list (spec
// desktop-app "Show the daemon and what needs the user in the menu bar"). The
// window reads that list through the query key every page shares and follows
// the daemon's change feed, which announces every change in the list (the
// daemon's attention watcher computes it once for every reader), so the tray
// learns of a change the moment it happens without a poll of its own. While
// the window is closed the shell reads the list itself.
import { useEffect } from "react";

import { useAttention } from "@/lib/hooks/useAttention";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { inDesktopShell, shellInvoke } from "@/lib/tauri";

/** Tell the shell the list's length (`tray::set_attention_count`). */
function reportCount(count: number): Promise<void> {
  return shellInvoke("set_attention_count", { count });
}

export function useTrayAttentionCount(): void {
  const inShell = inDesktopShell();
  useDaemonEvents({ enabled: inShell });
  const attention = useAttention({ enabled: inShell });
  const count = attention.data?.items.length;
  useEffect(() => {
    if (!inShell || count === undefined) return;
    reportCount(count).catch((e: unknown) => {
      console.error("Coffer: could not tell the desktop shell the attention count", e);
    });
  }, [inShell, count]);
}
