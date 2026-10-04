// frontend/src/components/FeatureGate.tsx
//
// The route guard of an experimental feature's pages. A switched-off feature
// looks absent (spec experimental-features "Close every surface of a
// switched-off feature"): while it is off, a deep link to one of its pages lands
// on the app's standard not-found page — no notice, no switch. While the
// daemon has not yet said whether the feature is on, nothing is rendered but
// the page loading fallback, so there is never a flash of the page or of the
// not-found page. The page itself is not mounted while the feature is off, so
// none of its requests are made.
import type { ReactNode } from "react";

import { PageFallback } from "@/components/PageFallback";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { useFeatureEnabled, type FeatureKey } from "@/lib/hooks/useFeatures";

interface Props {
  feature: FeatureKey;
  children: ReactNode;
  /** What a switched-off feature's page shows: the app's not-found page, passed in by the router. */
  notFound: ReactNode;
}

export function FeatureGate({ feature, children, notFound }: Props) {
  const status = useDaemonStatus();
  const enabled = useFeatureEnabled(feature);

  // A daemon that cannot be reached says nothing about the feature; the page
  // renders and the offline banner explains the rest, as on any other page.
  if (enabled === undefined && !status.isError) return <PageFallback />;
  if (enabled !== false) return <>{children}</>;
  return <>{notFound}</>;
}
