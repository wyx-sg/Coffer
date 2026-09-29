// src/components/credentials/SecretPendingNotice.tsx — what a dialog shows after a write answered 202.
//
// Replacing a value in use, or any standalone secret's value, does not
// replace it: the new value waits sealed until a person approves it in the
// desktop app (spec credentials "Hold a replaced value in use until a person
// approves it"). So the dialog says it is saved and waiting — never that it
// took effect — and offers the approvals sheet.
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

export function SecretPendingNotice({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <ShieldAlert className={cn("size-4", toneTextClass("warn"))} aria-hidden />
          {t("secrets.pending.title")}
        </DialogTitle>
        <DialogDescription>{t("secrets.pending.body")}</DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          {t("common.close")}
        </Button>
        <Button
          onClick={() => {
            onClose();
            openApprovalsSheet();
          }}
        >
          {t("credentials.approvals.review")}
        </Button>
      </DialogFooter>
    </>
  );
}
