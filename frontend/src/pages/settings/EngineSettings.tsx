// frontend/src/pages/settings/EngineSettings.tsx
//
// The Speech-to-text section of Settings › General (spec internal-engine "Show
// the speech-to-text pair in Settings › General"): the connection and model
// Coffer transcribes voice with, and the price-list refresh switch. The passes Coffer runs unattended
// are switched on the Memory page, not here.
import { useTranslation } from "react-i18next";

import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Skeleton } from "@/components/ui/skeleton";
import { useProviders } from "@/lib/hooks/useProviders";

import { PriceRefreshSetting } from "./PriceRefreshSetting";
import { SpeechToTextSettings } from "./SpeechToTextSettings";

export function EngineSettings() {
  const { t } = useTranslation();
  // Until the connections arrive, keep the section's shape rather than render
  // a picker that reads as unset.
  const { isPending } = useProviders();
  return (
    <SettingsSection
      title={t("settings.speechToText.title")}
      description={t("settings.speechToText.subtitle")}
      testId="speech-to-text-section"
    >
      {isPending ? (
        <div className="flex flex-col gap-2 py-2.5" data-testid="speech-to-text-loading">
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <>
          <SpeechToTextSettings />
          <PriceRefreshSetting />
        </>
      )}
    </SettingsSection>
  );
}
