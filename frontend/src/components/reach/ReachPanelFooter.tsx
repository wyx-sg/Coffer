// src/components/reach/ReachPanelFooter.tsx — the foot of ReachControl's panel: the count, Done, and the machine-local line.
//
// Foundations-Reach "Footer": the count on the left, the way out on the right,
// over a border-subtle rule. Split out of ReachControl to keep that file inside
// its size budget; it owns no state.
import { useTranslation } from "react-i18next";

import type { ReachMode } from "@/lib/reach/reachState";
import { Button } from "@/components/ui/button";

interface Props {
  /** The choice that reads as picked; `null` for an untouched bulk panel. */
  picked: ReachMode | null;
  selected: number;
  total: number;
  busy: boolean;
  onDone: () => void;
}

export function ReachPanelFooter({ picked, selected, total, busy, onDone }: Props) {
  const { t } = useTranslation();
  // Under "Every agent" the ticks are not the reach, so they get no count.
  const counted = picked === "restricted" || picked === "disabled";
  return (
    <>
      <div className="flex min-h-control-sm items-center justify-between gap-3 border-t border-border-subtle pt-2">
        <span className="text-xs text-text-muted">
          {counted ? t("scope.countOf", { selected, total }) : null}
        </span>
        {/* The one choice that stays open needs an explicit way out: Done
            commits the staged list exactly as closing does. */}
        {picked === "restricted" ? (
          <Button type="button" size="sm" disabled={busy} onClick={onDone}>
            {t("common.done")}
          </Button>
        ) : null}
      </div>
      {/* Quiet, not amber: a standing fact about where reach is kept, not a
          fault. Amber is for a scope that reaches nobody. */}
      <p className="text-xs text-text-muted" data-testid="reach-machine-local">
        {t("scope.machineLocal")}
      </p>
    </>
  );
}
