// frontend/src/pages/settings/SecretBoundaryCard.tsx
//
// Settings › Security, second card: whether a secret waits for approval before
// it goes somewhere new, and the way back to what waits (spec credentials
// "Hold a secret for a new destination until a person approves it"). The
// switch itself is not here: turning the protection off takes the desktop
// app's presence check, so the card only reports it and names the command.
import { useTranslation } from "react-i18next";

import { PendingApprovalsEntry } from "@/components/credentials/PendingApprovalsEntry";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSecretBoundarySettings } from "@/lib/hooks/useApprovals";

export function SecretBoundaryCard() {
  const { t } = useTranslation();
  const { data } = useSecretBoundarySettings();
  const on = data?.require_approval ?? true;
  return (
    <Card data-testid="secret-boundary-card">
      <CardHeader>
        <CardTitle>{t("settings.security.approvals.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {t("settings.security.approvals.description")}
        </p>
        <p className="text-sm">
          {on ? t("settings.security.approvals.on") : t("settings.security.approvals.off")}
        </p>
        <PendingApprovalsEntry />
      </CardContent>
    </Card>
  );
}
