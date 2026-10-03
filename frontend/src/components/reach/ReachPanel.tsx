// frontend/src/components/reach/ReachPanel.tsx
// The body of a ReachControl's popover: title, note, the three mode choices
// with their inline failure, the agent list and the footer.
import { useTranslation } from "react-i18next";

import { AgentPicker, type RowFailure } from "@/components/reach/AgentPicker";
import { ReachPanelFooter, type SaveState } from "@/components/reach/ReachPanelFooter";
import type { Failure } from "@/components/reach/useReachWrites";
import { WARNING_CLASS, type PickableAgent, type ReachMode } from "@/lib/reach/reachState";

interface Props {
  resourceName?: string;
  note?: string;
  choices: React.ReactNode;
  failure: Failure | null;
  registered: PickableAgent[];
  selected: string[];
  partial: string[];
  inactive: boolean;
  busy: boolean;
  picked: ReachMode | null;
  total: number;
  save: SaveState;
  onToggle: (uid: string, checked: boolean) => void;
  onApply?: () => void;
  applyDisabled: boolean;
}

export function ReachPanel({
  resourceName,
  note,
  choices,
  failure,
  registered,
  selected,
  partial,
  inactive,
  busy,
  picked,
  total,
  save,
  onToggle,
  onApply,
  applyDisabled,
}: Props) {
  const { t } = useTranslation();
  const summary =
    picked === "disabled"
      ? t("common.disabled")
      : picked === "everywhere"
        ? t("scope.everywhere")
        : picked === "restricted"
          ? t("scope.countOf", { selected: selected.length, total })
          : "";
  const rowFailure: RowFailure | null =
    failure?.uid !== undefined
      ? { uid: failure.uid, message: failure.message, onRetry: failure.retry }
      : null;
  return (
    <>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-text">{t("scope.availableTo")}</p>
        {resourceName ? <p className="truncate text-xs text-text-subtle">{resourceName}</p> : null}
      </div>

      {note ? <p className={WARNING_CLASS}>{note}</p> : null}

      <div
        role="radiogroup"
        aria-label={t("scope.choicesLabel")}
        className="border-b border-border-subtle pb-2.5"
      >
        {choices}
        {failure && failure.uid === undefined ? (
          <p
            role="alert"
            data-testid="scope-mode-failed"
            className="mt-1.5 flex items-center gap-1.5 text-xs text-danger"
          >
            <span className="min-w-0 flex-1">
              {t("scope.rowFailed")} — {failure.message}
            </span>
            <button type="button" className="shrink-0 font-label underline" onClick={failure.retry}>
              {t("common.retry")}
            </button>
          </p>
        ) : null}
      </div>

      <AgentPicker
        className="min-h-0 flex-1 overflow-y-auto"
        registered={registered}
        selected={selected}
        partial={partial}
        inactive={inactive}
        busy={busy}
        failure={rowFailure}
        onToggle={onToggle}
      />

      <ReachPanelFooter
        summary={summary}
        save={save}
        busy={busy}
        onApply={onApply}
        applyDisabled={applyDisabled}
      />
    </>
  );
}
