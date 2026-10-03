// src/components/secret/PendingApprovalsEntry.tsx
// A way back to the approvals sheet once it was dismissed: "N changes waiting
// for approval · Review", with what approving takes here — Touch ID or the
// login password in the Coffer app; in a browser, the app (rejecting works
// anywhere). Renders nothing while nothing waits. Used on the Secrets page and
// in Settings › Security.
import { ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { openApprovalsSheet, usePendingApprovals } from "@/lib/hooks/useApprovals";
import { presenceAvailable } from "@/lib/tauri";

export function PendingApprovalsEntry() {
  const { t } = useTranslation();
  const { data } = usePendingApprovals();
  const count = data?.approvals.length ?? 0;
  if (count === 0) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-3 rounded-lg border border-warning/30 bg-warning-soft px-3.5 py-2.5"
      data-testid="pending-approvals-entry"
    >
      <ShieldCheck className="size-4 shrink-0 text-warning" aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-semibold text-text">{t("secrets.approvals.title", { count })}</p>
        <p className="text-xs text-text-muted">
          {presenceAvailable()
            ? t("secrets.approvals.hintShell")
            : t("secrets.approvals.hintBrowser")}
        </p>
      </div>
      <Button variant="outline" size="sm" className="ml-auto" onClick={openApprovalsSheet}>
        {t("secrets.approvals.review")}
      </Button>
    </div>
  );
}
