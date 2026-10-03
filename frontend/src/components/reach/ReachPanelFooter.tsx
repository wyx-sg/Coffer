// src/components/reach/ReachPanelFooter.tsx — the foot of a reach panel: the summary on the left, the save state on the right.
//
// Foundations-Reach "Footer": over a border-subtle rule, the summary ("Off" /
// "All agents" / "1 of 2 agents" — the only place a count appears) on the
// left, and the save state on the right: a spinner and "Applying…" while a
// write runs, "✓ Saved" once it landed. Every change saves at once, so there is
// no Done button. It owns no state.
import { useTranslation } from "react-i18next";

import { Spinner } from "@/components/ui/spinner";
import type { SaveState } from "@/lib/reach/useReachWrites";

interface Props {
  summary: string;
  /** Omitted where nothing is written (a form's draft). */
  saveState?: SaveState;
  failed?: boolean;
}

export function ReachPanelFooter({ summary, saveState = "idle", failed = false }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-control-sm items-center justify-between gap-3 border-t border-border-subtle pt-2 text-xs">
      <span className="text-text-muted" data-testid="reach-summary">
        {summary}
      </span>
      <span role="status" className="inline-flex items-center gap-1.5">
        {failed ? (
          <span className="text-danger">{t("scope.failed")}</span>
        ) : saveState === "applying" ? (
          <>
            <Spinner />
            <span className="text-text-muted">{t("scope.applying")}</span>
          </>
        ) : saveState === "saved" ? (
          <span className="text-success">{`✓ ${t("scope.saved")}`}</span>
        ) : null}
      </span>
    </div>
  );
}
