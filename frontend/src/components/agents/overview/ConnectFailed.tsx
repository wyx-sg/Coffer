// src/components/agents/overview/ConnectFailed.tsx — the Connection card's failure strip (board 2.1.09).
import { useTranslation } from "react-i18next";
import { AlertTriangle, RotateCcw } from "lucide-react";

import { STATUS_TONE } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

const K = "agents.overviewTab.connection";

/** The last Connect from this window failed: why, and Try again (board 2.1.09). */
export function ConnectFailed({ reason, onRetry }: { reason: string; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className={cn(
        "ml-[46px] flex items-start gap-2.5 rounded-lg px-3 py-2.5",
        toneClass(STATUS_TONE.err),
      )}
    >
      <AlertTriangle aria-hidden className="mt-px size-4 shrink-0" />
      <span className="min-w-0 grow text-xs leading-normal text-text">
        {t(`${K}.connectFailed`, { reason })}
      </span>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RotateCcw aria-hidden />
        {t(`${K}.tryAgain`)}
      </Button>
    </div>
  );
}
