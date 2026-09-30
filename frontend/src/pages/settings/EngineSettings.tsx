// frontend/src/pages/settings/EngineSettings.tsx
//
// The Coffer's model section of Settings › General (spec web-ui "Choose
// Coffer's model in Settings › General", spec internal-engine "Show and change
// Coffer's model in Settings › General"): the models Coffer runs for its own
// work, not anything served to an agent.
//
// Two pickers — Coffer's engine and Speech to text — each a provider then a
// model from that provider's list, with a Test and a state line; the bound on
// one call to the engine sits under the engine picker. The passes Coffer runs
// unattended on that model are switched on the pages they upkeep — Knowledge's
// and Memory's Automatic popovers — not here.
//
// Speech to text is a picker of its own rather than a row borrowed from the
// engine's, because it runs on a SECOND connection flag with no fallback to the
// engine's (spec internal-engine "Transcribe speech on its own connection and
// model"). There is no embedding picker: knowledge is a directory of files an
// agent reads with its own tools, so there is no index for one to feed.
import { useTranslation } from "react-i18next";

import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Skeleton } from "@/components/ui/skeleton";
import { useProviders } from "@/lib/hooks/useProviders";

import { InternalEngineSettings } from "./InternalEngineSettings";
import { SpeechToTextSettings } from "./SpeechToTextSettings";

export function EngineSettings() {
  const { t } = useTranslation();
  // Both pickers list the same connections; until they arrive, keep the
  // section's shape rather than render pickers that read as unset.
  const { isPending } = useProviders();
  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        title={t("settings.cofferModel.title")}
        description={t("settings.cofferModel.subtitle")}
        testId="coffer-model-section"
      >
        {isPending ? (
          <div className="flex flex-col gap-2 py-2.5" data-testid="coffer-model-loading">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : (
          <>
            <InternalEngineSettings />
            <SpeechToTextSettings />
          </>
        )}
      </SettingsSection>
    </div>
  );
}
