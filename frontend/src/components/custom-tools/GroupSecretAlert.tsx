// src/components/custom-tools/GroupSecretAlert.tsx — the banner a group shows while its secret is missing
// or waits for approval: what fails, and the one way to fix it.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { KeyRound, Plus, TriangleAlert } from "lucide-react";

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
      <TriangleAlert aria-hidden />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <AlertTitle>{t("customTools.alert.missingTitle", { secret })}</AlertTitle>
          <AlertDescription>
            {t("customTools.alert.missingBody", { count: toolsOn(group.tools) })}
          </AlertDescription>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button asChild size="sm" variant="outline">
            <Link to="/secrets">
              <Plus aria-hidden />
              {t("customTools.alert.addSecret")}
            </Link>
          </Button>
          <Button size="sm" variant="outline" onClick={onChooseAnother}>
            {t("customTools.alert.chooseAnother")}
          </Button>
        </div>
      </div>
    </Alert>
  );
}
