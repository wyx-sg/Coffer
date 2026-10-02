// src/components/secret/ApprovalsBatchBar.tsx — answer several waiting changes at once.
//
// "Select all" and a count, then "Approve selected…" (which opens the review
// step — nothing is approved from here) and "Reject selected". Nothing is
// selected to begin with, so approving many is a deliberate act. In a browser
// Approve is disabled, naming the app; Reject works anywhere.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface Props {
  total: number;
  selected: number;
  inShell: boolean;
  busy: boolean;
  onSelectAll: (all: boolean) => void;
  onReview: () => void;
  onReject: () => void;
}

export function ApprovalsBatchBar({
  total,
  selected,
  inShell,
  busy,
  onSelectAll,
  onReview,
  onReject,
}: Props) {
  const { t } = useTranslation();
  const none = selected === 0;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="approvals-batch-bar">
      <label className="mr-auto flex items-center gap-2 text-xs text-text">
        <Checkbox
          checked={selected === total}
          indeterminate={selected > 0 && selected < total}
          onChange={(e) => onSelectAll(e.target.checked)}
        />
        {selected > 0
          ? t("secrets.approvals.batch.selected", { count: selected })
          : t("secrets.approvals.batch.selectAll", { count: total })}
      </label>
      <Button size="sm" variant="outline" disabled={none || busy} onClick={onReject}>
        {t("secrets.approvals.batch.rejectSelected", { count: selected })}
      </Button>
      {inShell ? (
        <Button size="sm" disabled={none || busy} onClick={onReview}>
          {t("secrets.approvals.batch.approveSelected", { count: selected })}
        </Button>
      ) : (
        <Tooltip>
          <TooltipTrigger asChild>
            {/* A disabled button fires no pointer events; the span carries the tooltip. */}
            <span tabIndex={0} title={t("secrets.approvals.approveInApp")}>
              <Button size="sm" disabled>
                {t("secrets.approvals.batch.approveSelected", { count: selected })}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>{t("secrets.approvals.approveInApp")}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
