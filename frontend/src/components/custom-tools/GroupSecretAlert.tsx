// src/components/custom-tools/GroupSecretAlert.tsx — the banner a group shows while its secret is missing
// or waits for approval: what fails, and the one way to fix it.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { KeyRound } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { toolsOn } from "@/lib/customTools/groups";

interface Props {
  group: CustomToolGroup;
  onChooseAnother: () => void;
}

export function GroupSecretAlert({ group, onChooseAnother }: Props) {
  const { t } = useTranslation();
  const secret = group.auth?.secret ?? "";
  if (group.secret_state === "pending_approval") {
    return (
      <Alert variant="warning">
        <KeyRound aria-hidden />
        <AlertTitle>{t("customTools.alert.pendingTitle", { secret })}</AlertTitle>
        <AlertDescription>{t("customTools.alert.pendingBody")}</AlertDescription>
      </Alert>
    );
  }
  if (group.secret_state !== "missing") return null;
  return (
    <Alert variant="warning">
      <KeyRound aria-hidden />
      <AlertTitle>{t("customTools.alert.missingTitle", { secret })}</AlertTitle>
      <AlertDescription>
        <p>{t("customTools.alert.missingBody", { count: toolsOn(group.tools) })}</p>
        <div className="mt-2 flex gap-2">
          <Button asChild size="sm">
            <Link to="/secrets">{t("customTools.alert.addSecret")}</Link>
          </Button>
          <Button size="sm" variant="outline" onClick={onChooseAnother}>
            {t("customTools.alert.chooseAnother")}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}
