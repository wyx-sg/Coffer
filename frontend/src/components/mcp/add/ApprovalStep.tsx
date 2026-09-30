// frontend/src/components/mcp/add/ApprovalStep.tsx — shown after an add whose
// secret the daemon holds for approval (202 from `POST /credentials`, spec
// secret secret boundary): the servers are registered, the secret takes
// effect once someone approves it in the Coffer app. Neither a success nor a
// failure, so it is said before the dialog lets go, with the way to approve.
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";

interface Props {
  /** The servers whose secrets wait. */
  names: string[];
  onDone: () => void;
}

export function ApprovalStep({ names, onDone }: Props) {
  const { t } = useTranslation();
  return (
    <>
      <Alert variant="warning">
        <AlertDescription>
          {t("mcp.add.approvalBody", { names: names.join(", ") })}
        </AlertDescription>
      </Alert>
      <DialogFooter>
        <Button variant="outline" onClick={() => openApprovalsSheet()}>
          {t("mcp.add.openApprovals")}
        </Button>
        <Button onClick={onDone}>{t("common.done")}</Button>
      </DialogFooter>
    </>
  );
}
