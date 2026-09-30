// frontend/src/components/FeatureGate.tsx
//
// What a page of an experimental feature renders while the feature is
// switched off on this machine (spec experimental-features "Close every
// surface of a switched-off feature"): a notice that says so, with a Switch
// on button that flips it right here — the same write as the switch on
// Settings → General (`useSetFeature`), which takes effect at once with no
// restart, so the page renders as soon as the daemon answers — and a way to
// open Settings. A feature `COFFER_FEATURES` pins cannot be switched from
// here, so the notice explains the pin instead and offers no button. The page
// itself is not mounted, so none of its requests are made.
//
// A bookmark or a typed URL is how anyone gets here — the sidebar entry is
// already gone — so the notice names the feature rather than answering "page
// not found" for a page that exists.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { FlaskConical } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import {
  useFeatureEnabled,
  useFeatureList,
  useSetFeature,
  type FeatureKey,
} from "@/lib/hooks/useFeatures";
import { useOpenSettings } from "@/lib/settingsModal";

export function FeatureGate({ feature, children }: { feature: FeatureKey; children: ReactNode }) {
  const status = useDaemonStatus();
  const enabled = useFeatureEnabled(feature);

  // A daemon that cannot be reached says nothing about the feature; the page
  // renders and the offline banner explains the rest, as on any other page.
  if (enabled === undefined && !status.isError) return <PageFallback />;
  if (enabled !== false) return <>{children}</>;
  return <SwitchedOff feature={feature} />;
}

function SwitchedOff({ feature }: { feature: FeatureKey }) {
  const { t } = useTranslation();
  const list = useFeatureList();
  const save = useSetFeature();
  const openSettings = useOpenSettings();

  const name = t(`settings.features.names.${feature}`, { defaultValue: feature });
  // Only the full registry says which layer decided the state; until it has
  // answered the button waits rather than offering a switch a pin would refuse.
  const pinned = list.data?.features.find((f) => f.key === feature)?.source === "pin";
  const settings = (
    <Button type="button" variant="outline" onClick={() => openSettings("general")}>
      {t("settings.features.openSettings")}
    </Button>
  );

  return (
    <EmptyState
      icon={FlaskConical}
      title={t("settings.features.offTitle", { name })}
      description={
        pinned
          ? t("settings.features.offPinned", { name })
          : t("settings.features.offBody", { name })
      }
      detail={save.error ? translateApiError(t, save.error) : undefined}
      action={
        pinned ? (
          settings
        ) : (
          <Button
            type="button"
            disabled={list.data === undefined || save.isPending}
            onClick={() => save.mutate({ key: feature, enabled: true })}
          >
            {save.isPending ? t("settings.features.switchingOn") : t("settings.features.switchOn")}
          </Button>
        )
      }
      secondaryAction={pinned ? undefined : settings}
    />
  );
}
