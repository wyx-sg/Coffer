// frontend/src/pages/settings/SecuritySettings.tsx
//
// Settings › Security (canvas 1.4.03): what is about this Mac only — the key
// that encrypts the vault's secrets and the token that guards the daemon (spec
// web-ui "Organise Settings into six tabs"). Three sections and a footer line, in the
// Settings row rhythm (label and description on the left, control on the right):
//
//   • Encryption — where the master key lives, whether it was read, the
//     development build's move switch, and the key backup.
//   • Access — the daemon access token: Show, Copy, Rotate.
//   • Approvals — whether a secret waits before going somewhere new.
//   • A footer line (no box) to the Secrets page, because no stored secret is listed,
//     added, revealed or deleted here.
import { useTranslation } from "react-i18next";
import { ArrowRight, KeyRound } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { AccessTokenRow } from "@/components/settings/security/AccessTokenRow";
import { EncryptionSection } from "@/components/settings/security/EncryptionSection";
import {
  SETTINGS_STACK,
  SettingsSection,
  SettingsTabHeader,
} from "@/components/settings/SettingsLayout";

import { SecretBoundaryCard } from "./SecretBoundaryCard";

export function SecuritySettings() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-5">
      <SettingsTabHeader
        title={t("settings.tabs.security")}
        intro={t("settings.security.subtitle")}
      />
      <div className={SETTINGS_STACK}>
        <EncryptionSection />
        <SettingsSection title={t("settings.security.access.title")}>
          <AccessTokenRow />
        </SettingsSection>
        <SecretBoundaryCard />
        <SecretsFooter />
      </div>
    </div>
  );
}

function SecretsFooter() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="flex items-center gap-2">
      <KeyRound className="size-3.5 text-text-muted" aria-hidden />
      <span className="text-sm text-text-muted">{t("settings.security.secretsFooter")}</span>
      <Button
        variant="link"
        size="sm"
        className="ml-auto px-0"
        // Replace the Settings entry rather than push over it: the modal is
        // gone once the page opens, and Back returns to where Settings was
        // opened from instead of reopening it.
        onClick={() => navigate("/secrets", { replace: true })}
      >
        {t("settings.security.manageInSecrets")}
        <ArrowRight aria-hidden />
      </Button>
    </div>
  );
}
