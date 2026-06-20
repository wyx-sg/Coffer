// frontend/src/components/skills/SkillVerifyDialog.tsx
// Replaces the old window.alert drift report with a styled dialog. On open it
// runs useVerifySkills and shows either "No drift detected." or a list of drift
// entries (skill_name, agent_name, kind, suggested_remedy). The endpoint always
// verifies every skill; an optional `skillNames` prop narrows the *displayed*
// entries to a chosen subset (per-row / bulk verify), so the OK state reflects
// just those skills.
//
// When drift is present a "Repair" button lets the user opt-in to auto-repair.
// After repair the dialog shows two sections: remediated entries and any
// remaining entries that still need manual action.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle2, Loader2, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { DriftEntryOut, RepairReportOut } from "@/lib/api/skills";
import { useRepairSkillDrift, useVerifySkills } from "@/lib/hooks/useSkills";

/** Renders a compact list of drift entries with the same row layout used in the
 *  verify report. */
function DriftEntryList({ entries }: { entries: DriftEntryOut[] }) {
  return (
    <ul className="space-y-2">
      {entries.map((d, i) => (
        <li
          key={`${d.skill_name}-${d.agent_name}-${i}`}
          className="space-y-1 rounded-md border bg-card/60 px-3 py-2 text-sm"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{d.skill_name}</span>
            <span className="text-muted-foreground">→</span>
            <span>{d.agent_name}</span>
            <Badge variant="outline">{d.kind}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">{d.suggested_remedy}</p>
        </li>
      ))}
    </ul>
  );
}

export function SkillVerifyDialog({
  open,
  onOpenChange,
  skillNames,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When set, only drift entries for these skill names are displayed. */
  skillNames?: string[];
}) {
  const { t } = useTranslation();
  const verify = useVerifySkills();
  const repair = useRepairSkillDrift();
  const { mutate, reset } = verify;

  // Holds the repair result once the user clicks Repair.
  const [repairResult, setRepairResult] = useState<RepairReportOut | null>(null);

  // Re-run the drift check each time the dialog opens; clear stale state on close.
  useEffect(() => {
    if (open) {
      mutate();
      setRepairResult(null);
      repair.reset();
    } else {
      reset();
      setRepairResult(null);
      repair.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mutate, reset]);

  // The endpoint verifies all skills; narrow to the chosen subset when asked.
  const allEntries = verify.data?.entries ?? [];
  const entries = skillNames
    ? allEntries.filter((d) => skillNames.includes(d.skill_name))
    : allEntries;

  const hasDrift = verify.isSuccess && entries.length > 0;

  function handleRepair() {
    repair.mutate(undefined, {
      onSuccess: (data) => {
        setRepairResult(data);
      },
    });
  }

  // After repair: show the FULL global result unfiltered — repair is system-wide
  // and must be presented consistently (all remediated + all remaining).
  const remediatedEntries = repairResult?.remediated ?? [];
  const remainingEntries = repairResult ? (repairResult.remaining.entries ?? []) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("skills.verify.title")}</DialogTitle>
          <DialogDescription>{t("skills.verify.subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-1">
          {verify.isError ? (
            <div className="flex items-start gap-3 py-2 text-sm text-destructive" role="alert">
              <AlertCircle className="mt-0.5 size-5 shrink-0" />
              <span>{translateApiError(t, verify.error)}</span>
            </div>
          ) : /* Show the spinner until the verify mutation has actually
                completed: when idle (before the open-effect fires mutate) the
                empty entries list would otherwise flash a false "no drift". */
          !verify.isSuccess ? (
            <div className="flex items-center gap-3 py-4 text-sm text-muted-foreground">
              <Loader2 className="size-5 animate-spin" />
              {t("skills.verify.checking")}
            </div>
          ) : repairResult !== null ? (
            /* Post-repair view: show remediated + remaining sections. */
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                {t("skills.verify.fixGlobalNote")}
              </p>
              {remediatedEntries.length > 0 && (
                <div className="space-y-2">
                  <p className="flex items-center gap-2 text-sm font-medium text-primary">
                    <CheckCircle2 className="size-4 shrink-0" />
                    {t("skills.verify.fixed", { count: remediatedEntries.length })}
                  </p>
                  <DriftEntryList entries={remediatedEntries} />
                </div>
              )}
              {remainingEntries.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-muted-foreground">
                    {t("skills.verify.fixRemaining")}
                  </p>
                  <DriftEntryList entries={remainingEntries} />
                </div>
              )}
              {remediatedEntries.length === 0 && remainingEntries.length === 0 && (
                <div className="flex items-center gap-2 py-2 text-sm font-medium">
                  <CheckCircle2 className="size-5 text-primary" />
                  {t("skills.verify.ok")}
                </div>
              )}
              {repair.isError && (
                <div
                  className="flex items-start gap-3 py-2 text-sm text-destructive"
                  role="alert"
                >
                  <AlertCircle className="mt-0.5 size-5 shrink-0" />
                  <span>{translateApiError(t, repair.error)}</span>
                </div>
              )}
            </div>
          ) : entries.length === 0 ? (
            <div className="flex items-center gap-2 py-2 text-sm font-medium">
              <CheckCircle2 className="size-5 text-primary" />
              {t("skills.verify.ok")}
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {t("skills.verify.found", { count: entries.length })}
              </p>
              <DriftEntryList entries={entries} />
              {repair.isError && (
                <div
                  className="flex items-start gap-3 py-2 text-sm text-destructive"
                  role="alert"
                >
                  <AlertCircle className="mt-0.5 size-5 shrink-0" />
                  <span>{translateApiError(t, repair.error)}</span>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          {hasDrift && repairResult === null && (
            <Button
              variant="outline"
              onClick={handleRepair}
              disabled={repair.isPending}
            >
              {repair.isPending ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  {t("skills.verify.fixing")}
                </>
              ) : (
                <>
                  <Wrench className="mr-2 size-4" />
                  {t("skills.verify.fix")}
                </>
              )}
            </Button>
          )}
          <Button onClick={() => onOpenChange(false)}>{t("common.done")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
