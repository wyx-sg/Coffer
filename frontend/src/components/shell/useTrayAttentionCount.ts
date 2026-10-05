// src/components/shell/useTrayAttentionCount.ts — keep the tray's count in step with the attention list.
//
// The menu bar's count is the length of the Overview's attention list (spec
// desktop-app "Show the daemon and what needs the user in the menu bar"). The
// shell reads that list on its own slow tick; while the window is open the
// page reads the same query key every page shares, so a resolve or an ignore
// anywhere — each invalidates it — reaches the tray as soon as the refetch
// lands. The short interval covers changes no mutation on this page made.
import { useEffect } from "react";

import { useAttention } from "@/lib/hooks/useAttention";
import { inDesktopShell, shellInvoke } from "@/lib/tauri";

/** How often the open window re-reads the list with nothing prompting it. */
const REFRESH_MS = 10_000;

/** Tell the shell the list's length (`tray::set_attention_count`). */
function reportCount(count: number): Promise<void> {
  return shellInvoke("set_attention_count", { count });
}

export function useTrayAttentionCount(): void {
  const inShell = inDesktopShell();
  const attention = useAttention({ enabled: inShell, refetchInterval: REFRESH_MS });
  const count = attention.data?.items.length;
  useEffect(() => {
    if (!inShell || count === undefined) return;
    reportCount(count).catch((e: unknown) => {
      console.error("Coffer: could not tell the desktop shell the attention count", e);
    });
  }, [inShell, count]);
}
