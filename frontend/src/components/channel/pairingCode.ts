// frontend/src/components/channel/pairingCode.ts
// What the pairing-code panel and the dialogs that host it share: a ticking
// clock, whether a code has run out, and the bot's handle read off its link.
import { useEffect, useState } from "react";

import type { PairingCode } from "@/lib/api/channels";

/** Re-render every `ms` so a countdown moves while the panel is open. */
export function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

/** Whether the code has run out. Ticks, so a dialog left open notices. */
export function usePairingExpired(code: PairingCode | undefined): boolean {
  const now = useNow(5_000);
  return code !== undefined && new Date(code.expires_at).getTime() - now <= 0;
}

/** The bot's handle, as far as the platform's link tells it (`t.me/<bot>?start=…`). */
export function botHandleOf(code: PairingCode | undefined): string | null {
  const match = /t\.me\/([^/?#]+)/.exec(code?.pair_url ?? "");
  return match ? match[1] : null;
}
