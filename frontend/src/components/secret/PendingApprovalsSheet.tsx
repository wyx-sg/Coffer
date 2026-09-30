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
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { OPEN_APPROVALS_EVENT, usePendingApprovals } from "@/lib/hooks/useApprovals";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { presenceAvailable } from "@/lib/tauri";
import { ApprovalCard } from "./ApprovalCard";
import { approvalsTitle } from "./secretRows";

export function PendingApprovalsSheet() {
  const { t } = useTranslation();
  const { data } = usePendingApprovals();
  const approvals = data?.approvals ?? [];
  // Ids the user has already seen and closed the sheet on.
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  const open = approvals.some((a) => !dismissed.has(a.id));
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

  const onOpenChange = (next: boolean) => {
    if (next) return;
    setDismissed((prev) => new Set([...prev, ...approvals.map((a) => a.id)]));
  };
  const single = approvals.length === 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{approvalsTitle(t, approvals, rows)}</DialogTitle>
          <DialogDescription className={single ? "sr-only" : undefined}>
            {inShell
              ? t("secrets.approvals.hintShell")
              : t("secrets.approvals.hintBrowser")}
          </DialogDescription>
        </DialogHeader>
        <ul className="max-h-[60vh] space-y-3 overflow-y-auto">
          {approvals.map((a) => (
            <ApprovalCard
              key={a.id}
              approval={a}
              row={rows.find((r) => r.ref === a.ref)}
              inShell={inShell}
              heading={single ? "title" : "card"}
            />
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
