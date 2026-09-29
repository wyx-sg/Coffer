// src/components/credentials/PendingApprovalsSheet.tsx
// The approvals a secret change waits on, shown wherever the user is.
//
// Mounted once in the app shell (`Layout`). It opens by itself when an approval
// it has not shown yet appears, and closing it dismisses what it showed — a
// newer approval, or `openApprovalsSheet()` (the "Review" entry on the Secrets
// page and in Settings › Security), opens it again. Each row says who asked, which secret, where
// it would go and what for; Reject is a REST call any host may make, Approve
// runs a presence check in the desktop shell, so a browser offers "Open in
// Coffer app" in its place (spec desktop-app "Release plaintext and approvals
// only after a presence check in the shell").
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Approval } from "@/lib/api/credentials";
import {
  OPEN_APPROVALS_EVENT,
  useApproveApproval,
  usePendingApprovals,
  useRejectApproval,
} from "@/lib/hooks/useApprovals";
import { presenceAvailable } from "@/lib/tauri";
import { formatDateTime } from "@/lib/utils";

export function PendingApprovalsSheet() {
  const { t } = useTranslation();
  const { data } = usePendingApprovals();
  const approvals = data?.approvals ?? [];
  // Ids the user has already seen and closed the sheet on.
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  const open = approvals.some((a) => !dismissed.has(a.id));
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t("credentials.approvals.title", { count: approvals.length })}</DialogTitle>
          <DialogDescription>
            {inShell
              ? t("credentials.approvals.hintShell")
              : t("credentials.approvals.hintBrowser")}
          </DialogDescription>
        </DialogHeader>
        <ul className="max-h-[60vh] space-y-3 overflow-y-auto">
          {approvals.map((a) => (
            <ApprovalRow key={a.id} approval={a} inShell={inShell} />
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

interface RowProps {
  approval: Approval;
  /** Whether Approve can run here (the desktop shell) or must send the user there. */
  inShell: boolean;
}

function ApprovalRow({ approval: a, inShell }: RowProps) {
  const { t } = useTranslation();
  const reject = useRejectApproval();
  const approve = useApproveApproval();
  const busy = reject.isPending || approve.isPending;
  const destination = [a.destination_kind, a.destination_label].filter(Boolean).join(" · ");

  const fields: [string, string | null][] = [
    [t("credentials.approvals.requestedBy"), a.requested_by],
    [t("credentials.approvals.secret"), a.ref],
    [
      t("credentials.approvals.destination"),
      destination ? (a.slot ? `${destination} (${a.slot})` : destination) : null,
    ],
    [t("credentials.approvals.target"), a.target],
  ];

  return (
    <li
      className="space-y-2 rounded-xl border border-border-subtle bg-surface-sunken p-3"
      data-testid="approval-row"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-text">{a.description}</p>
        <Badge variant="secondary">{t(`credentials.approvals.op.${a.op}`)}</Badge>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {fields
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-text-muted">{label}</dt>
              <dd className="break-all font-mono text-text">{value}</dd>
            </div>
          ))}
      </dl>
      <div className="flex items-center justify-between gap-2">
        <span className="text-2xs text-text-subtle">{formatDateTime(a.created_at)}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="danger" disabled={busy} onClick={() => reject.mutate(a.id)}>
            {t("credentials.approvals.reject")}
          </Button>
          {inShell ? (
            <Button size="sm" disabled={busy} onClick={() => approve.mutate(a.id)}>
              {t("credentials.approvals.approve")}
            </Button>
          ) : (
            <Button size="sm" variant="outline" disabled>
              {t("credentials.presence.openInApp")}
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}
