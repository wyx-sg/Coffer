// src/components/secret/PendingApprovalsSheet.tsx
// The approvals a secret change waits on, shown wherever the user is.
//
// Mounted once in the app shell (`Layout`). It opens by itself when an approval
// it has not shown yet appears, and closing it dismisses what it showed — a
// newer approval, or `openApprovalsSheet()` (the "Review" entry on the Secrets
// page and in Settings › Security), opens it again. One waiting change is the
// dialog's question ("Approve a new value for github-token?"); several are
// listed, each as its own question. Reject is a REST call any host may make;
// Approve runs a presence check in the desktop shell, so a browser shows it
// disabled, naming the app (spec desktop-app "Release plaintext and approvals
// only after a presence check in the shell").
//
// With two or more waiting, each card has a checkbox (none selected to begin
// with) and a bar offers "Approve selected…" and "Reject selected". Approving
// opens a review step that lists every change the one confirmation covers; the
// shell's presence check then approves exactly that list, and the same rows
// show what happened to each (spec secret "Approve several bindings in one
// confirmation").
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Approval, ApprovalBatchResult } from "@/lib/api/secret";
import {
  OPEN_APPROVALS_EVENT,
  useApproveApprovals,
  usePendingApprovals,
  useRejectApprovals,
} from "@/lib/hooks/useApprovals";
import { useToast } from "@/components/ui/toast";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { presenceAvailable } from "@/lib/tauri";
import { ApprovalCard } from "./ApprovalCard";
import { ApprovalsBatchBar } from "./ApprovalsBatchBar";
import { ApprovalsBatchReview } from "./ApprovalsBatchReview";
import { approvalsTitle } from "./secretRows";

export function PendingApprovalsSheet() {
  const { t } = useTranslation();
  const { data } = usePendingApprovals();
  const approvals = data?.approvals ?? [];
  // Ids the user has already seen and closed the sheet on.
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  // Which of the waiting changes are ticked (none to begin with), and the batch
  // being confirmed: what the review listed, then what became of each.
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const [batch, setBatch] = useState<{
    approvals: Approval[];
    results: ApprovalBatchResult[] | null;
  } | null>(null);
  const approveMany = useApproveApprovals();
  const rejectMany = useRejectApprovals();
  const { toast } = useToast();
  const open = batch !== null || approvals.some((a) => !dismissed.has(a.id));
  // What each secret is used by — read only while something waits.
  const secrets = useSecrets(approvals.length > 0);
  const rows = secrets.data?.refs ?? [];
  const inShell = presenceAvailable();
  // "Review" on the Secrets page or in Settings › Security brings back what
  // was dismissed.
  useEffect(() => {
    const reopen = () => setDismissed(new Set());
    window.addEventListener(OPEN_APPROVALS_EVENT, reopen);
    return () => window.removeEventListener(OPEN_APPROVALS_EVENT, reopen);
  }, []);

  const chosen = approvals.filter((a) => selected.has(a.id));
  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  const onConfirmBatch = () => {
    if (!batch) return;
    approveMany.mutate(
      batch.approvals.map((a) => a.id),
      { onSuccess: (done) => setBatch({ ...batch, results: done.results }) },
    );
  };
  const onRejectSelected = () =>
    rejectMany.mutate(
      chosen.map((a) => a.id),
      {
        onSuccess: (done) => {
          setSelected(new Set());
          toast.success(
            t("secrets.approvals.batch.rejectedCount", {
              count: done.results.filter((r) => r.outcome === "rejected").length,
            }),
          );
        },
      },
    );
  const finishBatch = () => {
    setBatch(null);
    setSelected(new Set());
  };

  const onOpenChange = (next: boolean) => {
    if (next) return;
    if (batch) {
      // Leaving the review answers nothing; leaving the outcome is done with it.
      finishBatch();
      return;
    }
    setDismissed((prev) => new Set([...prev, ...approvals.map((a) => a.id)]));
  };
  const single = approvals.length === 1;
  const title = batch
    ? batch.results
      ? t("secrets.approvals.batch.resultTitle")
      : t("secrets.approvals.batch.reviewTitle", { count: batch.approvals.length })
    : approvalsTitle(t, approvals, rows);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className={single || batch ? "sr-only" : undefined}>
            {inShell ? t("secrets.approvals.hintShell") : t("secrets.approvals.hintBrowser")}
          </DialogDescription>
        </DialogHeader>
        {batch ? (
          <ApprovalsBatchReview
            approvals={batch.approvals}
            rows={rows}
            results={batch.results}
            busy={approveMany.isPending}
            onBack={() => setBatch(null)}
            onConfirm={onConfirmBatch}
            onDone={finishBatch}
          />
        ) : (
          <>
            {single ? null : (
              <ApprovalsBatchBar
                total={approvals.length}
                selected={chosen.length}
                inShell={inShell}
                busy={rejectMany.isPending}
                onSelectAll={(all) =>
                  setSelected(all ? new Set(approvals.map((a) => a.id)) : new Set())
                }
                onReview={() => setBatch({ approvals: chosen, results: null })}
                onReject={onRejectSelected}
              />
            )}
            <ul className="max-h-[60vh] space-y-3 overflow-y-auto">
              {approvals.map((a) => (
                <ApprovalCard
                  key={a.id}
                  approval={a}
                  row={rows.find((r) => r.ref === a.ref)}
                  inShell={inShell}
                  heading={single ? "title" : "card"}
                  selected={selected.has(a.id)}
                  onSelectedChange={single ? undefined : (on) => toggle(a.id, on)}
                />
              ))}
            </ul>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
