// src/lib/api/features.ts — request functions for the experimental-feature registry (spec experimental-features).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type Feature = components["schemas"]["FeatureOut"];
export type FeatureList = components["schemas"]["FeatureListOut"];

export const featuresApi = {
  /** The registry with each feature's state and the layer that decided it. */
  list: (): Promise<FeatureList> => unwrap(getApiClient().GET("/daemon/features")),
  /** Switch one feature on or off on this machine. */
  set: (key: string, enabled: boolean): Promise<Feature> =>
    unwrap(
      getApiClient().PUT("/daemon/features/{key}", {
        params: { path: { key } },
        body: { enabled },
      }),
    ),
  /** Forget this machine's setting, so the feature is off by default again. */
  reset: (key: string): Promise<Feature> =>
    unwrap(getApiClient().DELETE("/daemon/features/{key}", { params: { path: { key } } })),
};
