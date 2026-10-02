// frontend/src/pages/settings/SecretBoundaryCard.tsx
//
// Settings › Security › Approvals: whether a secret waits for approval before
// it goes somewhere new, and the way back to what waits (spec secret
// "Hold a secret for a new destination until a person approves it").
//
// Turning the requirement ON needs nobody: it only narrows. Turning it OFF
// widens where secrets may go, so it is applied through the desktop app's
// presence check ("Turn the protection off only through the desktop app"):
// the switch is disabled with its reason in a browser tab, and in the app it
// asks for a confirmation that names the consequence before the check.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { PendingApprovalsEntry } from "@/components/secret/PendingApprovalsEntry";
import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  useSecretBoundarySettings,
  useTurnOffProtection,
  useTurnOnProtection,
} from "@/lib/hooks/useApprovals";
import { presenceAvailable } from "@/lib/tauri";
import { cn } from "@/lib/utils";

export function SecretBoundaryCard() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data } = useSecretBoundarySettings();
  const turnOn = useTurnOnProtection();
  const turnOff = useTurnOffProtection();
  const [confirming, setConfirming] = useState(false);
  const loaded = data !== undefined;
  const on = data?.require_approval ?? true;
  const inApp = presenceAvailable();
  const busy = turnOn.isPending || turnOff.isPending;
  const label = t("settings.security.approvals.title");

  const change = (checked: boolean) => {
    if (checked) {
      turnOn.mutate(undefined, {
        onError: (e) => toast.error(translateApiError(t, e)),
      });
    } else {
      setConfirming(true);
    }
  };

  return (
    <SettingsSection title={t("settings.security.approvals.section")} testId="secret-boundary-card">
      <SettingRow
        label={label}
        description={t("settings.security.approvals.description")}
        status={
          <span className={cn("text-xs", on ? "text-text-muted" : "text-warning")}>
            {on ? t("settings.security.approvals.on") : t("settings.security.approvals.off")}
          </span>
        }
      >
        {!inApp && on ? (
          <span className="text-xs text-text-muted">
            {t("settings.security.approvals.onlyInApp")}
          </span>
        ) : null}
        <Switch
          checked={on}
          disabled={!loaded || busy || (on && !inApp)}
          onCheckedChange={change}
          aria-label={label}
        />
      </SettingRow>
      <div className="pt-1 empty:hidden">
        <PendingApprovalsEntry />
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("settings.security.approvals.turnOffTitle")}
        description={t("settings.security.approvals.turnOffBody")}
        confirmLabel={t("settings.security.approvals.turnOffConfirm")}
        pendingLabel={t("settings.security.approvals.turnOffPending")}
        errorTitle={t("settings.security.approvals.failed")}
        onConfirm={() => turnOff.mutateAsync()}
      >
        <p className="text-xs text-text-muted">{t("settings.security.approvals.turnOffHint")}</p>
      </ConfirmDialog>
    </SettingsSection>
  );
}
