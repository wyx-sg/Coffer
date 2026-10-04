// frontend/src/pages/settings/EngineSettings.tsx
//
// The Speech-to-text section of Settings › General (spec internal-engine "Show
// the speech-to-text pair in Settings › General"): the connection and model
// Coffer transcribes voice with, and the price-list refresh switch. The passes Coffer runs unattended
// are switched on the Memory page, not here.
import { useTranslation } from "react-i18next";

import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Skeleton } from "@/components/ui/skeleton";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { useProviders } from "@/lib/hooks/useProviders";

import { PriceRefreshSetting } from "./PriceRefreshSetting";
import { SpeechToTextSettings } from "./SpeechToTextSettings";

/** The section exists only while the Models feature is on: speech to text is a
 *  connection of a model provider, so with it off there is nothing to choose
 *  and the section is absent. */
export function EngineSettings() {
  const models = useFeatureEnabled("models");
  return models === true ? <EngineSection /> : null;
}

function EngineSection() {
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
