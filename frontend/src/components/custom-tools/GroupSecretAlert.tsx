// src/components/custom-tools/GroupSecretAlert.tsx — the banner a group shows while a header's secret is missing
// (4.2.01: Add secret · Choose another), waits for approval (4.2.23: Open approvals) or was refused (4.2.29:
// Ask again, which in the desktop app asks for Touch ID at once) — no hand-off: only a person can add or
// approve a secret.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Plus } from "lucide-react";

import { ReplaceSecretDialog } from "@/components/secret/ReplaceSecretDialog";
import { useSecretChoices } from "@/components/secret/useSecretChoices";
import { secretRef } from "@/components/secret/secretValue";
import { Button } from "@/components/ui/button";
import type { CustomToolGroup } from "@/lib/api/customTools";
import type { SecretRef } from "@/lib/api/secret";
import { toolsOn } from "@/lib/customTools/groups";
import { secretInState } from "./headerRows";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { useAskAgainForGroup, useRefreshCustomTools } from "@/lib/hooks/useCustomTools";
import { GroupBanner } from "./GroupBanner";

interface Props {
  group: CustomToolGroup;
  onChooseAnother: () => void;
}

export function GroupSecretAlert({ group, onChooseAnother }: Props) {
  const { t } = useTranslation();
  const refresh = useRefreshCustomTools(group.name);
  const { rowOf, displayOf } = useSecretChoices();
  const [adding, setAdding] = useState(false);
  const askAgain = useAskAgainForGroup(group);
  if (group.secret_state === "rejected") {
    const secret = secretInState(group, "rejected");
    return (
      <GroupBanner
        tint="warn"
        icon={KeyRound}
        testId="group-banner-refused"
        title={t("customTools.alert.rejectedTitle", { secret: displayOf(secret) })}
        actions={
          <Button
            size="sm"
            variant="outline"
            disabled={askAgain.isPending}
            onClick={() => askAgain.mutate()}
          >
            {t("customTools.alert.askAgain")}
          </Button>
        }
      >
        {t("customTools.alert.rejectedBody")}
      </GroupBanner>
    );
  }
  if (group.secret_state === "pending_approval") {
    const secret = secretInState(group, "pending_approval");
    return (
      <GroupBanner
        tint="warn"
        icon={KeyRound}
        testId="group-banner-approval"
        title={t("customTools.alert.pendingTitle", { secret: displayOf(secret) })}
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
        title={t("customTools.alert.missingTitle", { secret: displayOf(secret) })}
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
      <ReplaceSecretDialog
        row={adding ? (rowOf(secret) ?? uncitedRow(secret)) : null}
        onOpenChange={(open) => {
          setAdding(open);
          if (!open) refresh();
        }}
      />
    </>
  );
}

/** The group cites this secret by name but the list has no row for it yet: a value is stored under
 *  exactly the name the group cites, never one a person types. */
function uncitedRow(secret: string): SecretRef {
  return {
    ref: secretRef(secret),
    present: false,
    locked: false,
    bindings: [],
    cited_by: [],
    mentioned_by_skills: [],
    created_at: null,
    last_used_at: null,
    readable_by_local_processes: false,
    local_access: null,
    unreferenced: false,
    uri: null,
    label: null,
    description: null,
    created_for: null,
  };
}
