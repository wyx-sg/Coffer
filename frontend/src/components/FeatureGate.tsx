// frontend/src/components/FeatureGate.tsx
//
// What a page of an experimental feature renders while the feature is
// switched off on this machine (spec experimental-features "Close every
// surface of a switched-off feature"): a notice that says so and links to the
// one place it is switched back on, Settings → General. The page itself is not
// mounted, so none of its requests are made.
//
// A bookmark or a typed URL is how anyone gets here — the sidebar entry is
// already gone — so the notice names the feature rather than answering "page
// not found" for a page that exists.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { FlaskConical } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import { Button } from "@/components/ui/button";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { useFeatureEnabled, type FeatureKey } from "@/lib/hooks/useFeatures";

export function FeatureGate({ feature, children }: { feature: FeatureKey; children: ReactNode }) {
  const { t } = useTranslation();
  const status = useDaemonStatus();
  const enabled = useFeatureEnabled(feature);

  // A daemon that cannot be reached says nothing about the feature; the page
  // renders and the offline banner explains the rest, as on any other page.
  if (enabled === undefined && !status.isError) return <PageFallback />;
  if (enabled !== false) return <>{children}</>;

  const name = t(`settings.features.names.${feature}`);
  return (
    <EmptyState
      icon={FlaskConical}
      title={t("settings.features.offTitle", { name })}
      description={t("settings.features.offBody", { name })}
      action={
        <Button asChild variant="outline" size="sm">
          <Link to="/settings/general">{t("settings.features.offCta")}</Link>
        </Button>
      }
    />
  );
}
