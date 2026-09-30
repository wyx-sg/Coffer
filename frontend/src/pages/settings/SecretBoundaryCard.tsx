// frontend/src/pages/settings/SecretBoundaryCard.tsx
//
// Settings › Security › Approvals: whether a secret waits for approval before
// it goes somewhere new, and the way back to what waits (spec secret
// "Hold a secret for a new destination until a person approves it"). The
// switch itself is not here: turning the protection off takes the desktop
// app's presence check, so the section only reports it and names the command.
import { useTranslation } from "react-i18next";

import { PendingApprovalsEntry } from "@/components/secret/PendingApprovalsEntry";
import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { StatusWord } from "@/components/status/StatusWord";
import { useSecretBoundarySettings } from "@/lib/hooks/useApprovals";

export function SecretBoundaryCard() {
  const { t } = useTranslation();
  const { data } = useSecretBoundarySettings();
  const on = data?.require_approval ?? true;
  return (
    <SettingsSection title={t("settings.security.approvals.section")} testId="secret-boundary-card">
      <SettingRow
        label={t("settings.security.approvals.title")}
        description={t("settings.security.approvals.description")}
        status={
          <span className="text-xs text-text-muted">
            {on ? t("settings.security.approvals.on") : t("settings.security.approvals.off")}
          </span>
        }
      >
        <StatusWord tone={on ? "ok" : "warn"}>
          {on ? t("settings.security.approvals.onWord") : t("settings.security.approvals.offWord")}
        </StatusWord>
      </SettingRow>
      <div className="pt-1 empty:hidden">
        <PendingApprovalsEntry />
      </div>
    </SettingsSection>
  );
}
