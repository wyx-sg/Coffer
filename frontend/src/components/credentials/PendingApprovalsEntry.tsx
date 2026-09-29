// src/components/credentials/PendingApprovalsEntry.tsx
// A way back to the approvals sheet once it was dismissed: "N changes waiting
// for approval · Review". Renders nothing while nothing waits. Used on the
// Secrets page and in Settings › Security.
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { openApprovalsSheet, usePendingApprovals } from "@/lib/hooks/useApprovals";

export function PendingApprovalsEntry() {
  const { t } = useTranslation();
  const { data } = usePendingApprovals();
  const count = data?.approvals.length ?? 0;
  if (count === 0) return null;
  return (
    <div
      className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-4 py-3"
      data-testid="pending-approvals-entry"
    >
      <p className="flex items-center gap-2 text-sm">
        <ShieldAlert className="size-4 text-status-warn" aria-hidden />
        {t("credentials.approvals.title", { count })}
      </p>
      <Button variant="outline" size="sm" onClick={openApprovalsSheet}>
        {t("credentials.approvals.review")}
      </Button>
    </div>
  );
}
