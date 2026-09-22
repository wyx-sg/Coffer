// src/components/FloatingBanners.tsx — the one fixed slot every app-wide
// banner is drawn in.
//
// It exists because two of them can be up at once and they used to be drawn on
// top of each other. Each owned an identical `fixed inset-x-0 top-4` wrapper,
// so whichever painted second hid the first entirely. The pairing was assumed
// impossible — an unreachable daemon answers no sync status — but
// `DaemonOfflineBanner` also fires on **version skew**, where the daemon
// answers everything perfectly well, and again for the moment a newly-failed
// status query spends retrying while the last good round is still cached.
//
// So the slot is a column, and a banner is just a card. Stacking is the right
// answer rather than choosing between them: an out-of-date daemon and a vault
// that stopped converging are two different things to do something about, and
// hiding either one behind the other is how a user ends up fixing only the one
// that happened to paint last.
//
// `pointer-events-none` on the column lets clicks through the empty gutter;
// each card re-enables them for itself.
import type { ReactNode } from "react";

export function FloatingBanners({ children }: { children: ReactNode }) {
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2 px-4">
      {children}
    </div>
  );
}
