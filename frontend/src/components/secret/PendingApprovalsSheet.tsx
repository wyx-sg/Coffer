// src/components/secret/PendingApprovalsSheet.tsx
// The approvals a secret change waits on, shown wherever the user is.
//
// Mounted once in the app shell (`Layout`). It opens by itself when an approval it has not shown
// yet appears, and closing it dismisses what it showed — a newer approval, or
// `openApprovalsSheet()` (the banners' Review on Secrets, the Overview row, Settings › Security)
// opens it again. One waiting change or many are the same 1060-wide table (Change · Secret · Goes
// to · Requested by · At) with a header box that selects them all. The footer reads "2 of 3
// selected" and offers Reject N and Approve N… (with nothing ticked they act on all). Reject is a
// REST call any host may make; Approve runs a presence check in the desktop shell, so a browser
// shows it disabled, naming the app (spec desktop-app "Release plaintext and approvals only after
// a presence check in the shell"). Approving several runs one presence check that signs over
// exactly the ticked list, and the same dialog turns into a per-change result (spec secret
// "Approve several bindings in one confirmation").
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useToast } from "@/components/ui/toast";
import type { Approval, ApprovalBatchResult } from "@/lib/api/secret";
import {
  OPEN_APPROVALS_EVENT,
  useApproveApproval,
  useApproveApprovals,
  usePendingApprovals,
  useRejectApprovals,
} from "@/lib/hooks/useApprovals";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { presenceAvailable } from "@/lib/tauri";
import { ApprovalsList, ApprovalsResult } from "./ApprovalsTable";
import { approvalSecretName } from "./secretRows";

interface Outcome {
  approvals: Approval[];
  results: ApprovalBatchResult[];
}

export function PendingApprovalsSheet() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data } = usePendingApprovals();
  const approvals = data?.approvals ?? [];
  // Ids the user has already seen and closed the sheet on.
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  // Which of the waiting changes are ticked (none to begin with), and what became of a batch.
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const approveOne = useApproveApproval();
  const approveMany = useApproveApprovals();
  const rejectMany = useRejectApprovals();
  const open = outcome !== null || approvals.some((a) => !dismissed.has(a.id));
  // What each secret is used by — read only while something waits.
  const secrets = useSecrets(approvals.length > 0);
  const rows = secrets.data?.refs ?? [];
  const inShell = presenceAvailable();
  const approving = approveOne.isPending || approveMany.isPending;
  const busy = approving || rejectMany.isPending;
  // "Review" on Secrets, Overview or Settings › Security brings back what was dismissed.
  useEffect(() => {
    const reopen = () => setDismissed(new Set());
    window.addEventListener(OPEN_APPROVALS_EVENT, reopen);
    return () => window.removeEventListener(OPEN_APPROVALS_EVENT, reopen);
  }, []);

  // Only changes still waiting count as ticked.
  const chosen = approvals.filter((a) => selected.has(a.id));
  const target = chosen.length > 0 ? chosen : approvals;
  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const onReject = () =>
    rejectMany.mutate(
      target.map((a) => a.id),
      {
        onSuccess: (done) => {
          setSelected(new Set());
          const rejected = target.filter((a) =>
            done.results.some((r) => r.id === a.id && r.outcome === "rejected"),
          );
          const only = rejected.length === 1 ? rejected[0] : null;
          toast.success(
            only
              ? t(`secrets.approvals.rejected.${only.op}`, {
                  name: approvalSecretName(only, rows),
                  destination: only.destination_label ?? "",
                })
              : t("secrets.approvals.batch.rejectedCount", { count: rejected.length }),
          );
        },
      },
    );
  const onApprove = () => {
    const asked = target;
    if (asked.length === 1) {
      const [only] = asked;
      approveOne.mutate(only.id, {
        onSuccess: () => {
          setSelected(new Set());
          toast.success(
            t(`secrets.approvals.approved.${only.op}`, {
              name: approvalSecretName(only, rows),
              destination: only.destination_label ?? "",
            }),
          );
        },
      });
      return;
    }
    approveMany.mutate(
      asked.map((a) => a.id),
      {
        onSuccess: (done) => {
          setSelected(new Set());
          setOutcome({ approvals: asked, results: done.results });
        },
      },
    );
  };

  const onOpenChange = (next: boolean) => {
    if (next || busy) return;
    if (outcome) {
      // The result is done with; whatever was skipped is still waiting and shows again.
      setOutcome(null);
      return;
    }
    setDismissed((prev) => new Set([...prev, ...approvals.map((a) => a.id)]));
  };

  const approved = outcome?.results.filter((r) => r.outcome === "approved").length ?? 0;
  const total = approvals.length;
  const picked = chosen.length;
  const approveLabel =
    picked > 0
      ? t("secrets.approvals.approveN", { count: picked })
      : total === 1
        ? t("secrets.approvals.approveEllipsis")
        : t("secrets.approvals.approveAll", { count: total });
  const rejectLabel =
    picked > 0
      ? t("secrets.approvals.rejectN", { count: picked })
      : total === 1
        ? t("secrets.approvals.reject")
        : t("secrets.approvals.rejectAll");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[1060px]">
        {outcome ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("secrets.approvals.batch.resultTitle", {
                  approved,
                  count: outcome.approvals.length,
                })}
              </DialogTitle>
              <DialogDescription>{t("secrets.approvals.batch.resultHint")}</DialogDescription>
            </DialogHeader>
            <ApprovalsResult approvals={outcome.approvals} rows={rows} results={outcome.results} />
            <DialogFooter className="items-center">
              <span className="mr-auto text-xs text-text-muted">
                {t("secrets.approvals.batch.recorded")}
              </span>
              <Button onClick={() => setOutcome(null)}>{t("common.done")}</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{t("secrets.approvals.title", { count: total })}</DialogTitle>
              <DialogDescription>
                {inShell
                  ? t("secrets.approvals.subtitleShell")
                  : t("secrets.approvals.subtitleBrowser")}
              </DialogDescription>
            </DialogHeader>
            <ApprovalsList
              approvals={approvals}
              rows={rows}
              selected={selected}
              onToggle={toggle}
              onToggleAll={(on) =>
                setSelected(on ? new Set(approvals.map((a) => a.id)) : new Set())
              }
            />
            <DialogFooter className="items-center">
              <span className="mr-auto text-xs text-text-muted">
                {picked > 0
                  ? t("secrets.approvals.selectedOf", { count: picked, total })
                  : t("secrets.approvals.selectHint")}
              </span>
              <Button variant="outline" disabled={busy || total === 0} onClick={onReject}>
                {rejectLabel}
              </Button>
              {inShell ? (
                <Button disabled={busy || total === 0} loading={approving} onClick={onApprove}>
                  {approveLabel}
                </Button>
              ) : (
                <Tooltip>
                  <TooltipTrigger asChild>
                    {/* A disabled button fires no pointer events; the span carries the tooltip. */}
                    <span tabIndex={0} title={t("secrets.approvals.approveInApp")}>
                      <Button disabled>{approveLabel}</Button>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{t("secrets.approvals.approveInApp")}</TooltipContent>
                </Tooltip>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
