// src/components/custom-tools/GroupSecretAlert.tsx — the banner a group shows while a header's secret is missing
// (4.2.01: Add secret · Choose another) or waits for approval (4.2.23: Open approvals, no hand-off — only a
// person can add or approve a secret).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Plus } from "lucide-react";

import { NewSecretDialog } from "@/components/secret/NewSecretDialog";
import { Button } from "@/components/ui/button";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { toolsOn } from "@/lib/customTools/groups";
import { secretInState } from "./headerRows";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { useRefreshCustomTools } from "@/lib/hooks/useCustomTools";
import { GroupBanner } from "./GroupBanner";

interface Props {
  group: CustomToolGroup;
  onChooseAnother: () => void;
}

export function GroupSecretAlert({ group, onChooseAnother }: Props) {
  const { t } = useTranslation();
  const refresh = useRefreshCustomTools(group.name);
  const [adding, setAdding] = useState(false);
  if (group.secret_state === "pending_approval") {
    const secret = secretInState(group, "pending_approval");
    return (
      <GroupBanner
        tint="warn"
        icon={KeyRound}
        testId="group-banner-approval"
        title={t("customTools.alert.pendingTitle", { secret })}
        actions={
          <Button size="sm" variant="outline" onClick={openApprovalsSheet}>
            {t("customTools.alert.openApprovals")}
          </Button>
        }
      >
        {t("customTools.alert.pendingBody")}
      </GroupBanner>
    );
  }
  if (group.secret_state !== "missing") return null;
  const secret = secretInState(group, "missing");
  return (
    <>
      <GroupBanner
        tint="warn"
        icon={KeyRound}
        testId="group-banner-secret"
        title={t("customTools.alert.missingTitle", { secret })}
        actions={
          <>
            <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
              <Plus aria-hidden />
              {t("customTools.alert.addSecret")}
            </Button>
            <Button size="sm" variant="outline" onClick={onChooseAnother}>
              {t("customTools.alert.chooseAnother")}
            </Button>
          </>
        }
      >
        {t("customTools.alert.missingBody", { count: toolsOn(group.tools) })}
      </GroupBanner>
      <NewSecretDialog
        open={adding}
        onOpenChange={setAdding}
        defaultName={secret}
        onCreated={refresh}
      />
    </>
  );
}
