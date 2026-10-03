// src/components/reach/ReachPanelFooter.tsx — the foot of ReachControl's panel: the summary on the left, the save state (or Apply) on the right.
//
// Foundations 0.7.02 "Footer": left, what the reach is in a few words (Off /
// All agents / "1 of 2 agents"); right, whether the last change landed
// (Saving… / ✓ Saved / Couldn't save). A bulk panel has no save state — it
// applies on a button — so it shows Apply there instead. Split out of
// ReachControl to keep that file inside its size budget; it owns no state.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

export type SaveState = "idle" | "saving" | "saved" | "failed";

interface Props {
  summary: string;
  save: SaveState;
  /** Set on a bulk panel: shows Apply (disabled while `busy`) in place of the
   *  save state. */
  onApply?: () => void;
  applyDisabled?: boolean;
  busy?: boolean;
}

export function ReachPanelFooter({ summary, save, onApply, applyDisabled, busy }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-control-sm items-center justify-between gap-3 border-t border-border-subtle pt-2">
      <span className="text-xs text-text-muted" data-testid="reach-summary">
        {summary}
      </span>
      {onApply ? (
        <Button type="button" size="sm" disabled={busy || applyDisabled} onClick={onApply}>
          {t("scope.apply")}
        </Button>
      ) : (
        <span
          role="status"
          data-testid="reach-save-state"
          className={save === "failed" ? "text-xs text-danger" : "text-xs text-text-muted"}
        >
          {save === "saving"
            ? t("common.saving")
            : save === "saved"
              ? `✓ ${t("common.saved")}`
              : save === "failed"
                ? t("scope.saveFailed")
                : null}
        </span>
      )}
    </div>
  );
}
