// frontend/src/lib/hooks/useFeatures.ts
//
// The experimental features (spec experimental-features): which of them are
// switched on on this machine, and the switch itself.
//
// Two reads, on purpose. Every surface that only needs "is it on?" — the
// sidebar, the gated routes, a query that belongs to a feature — reads the
// `features` map off `GET /daemon/status`, which the shell already polls for the
// offline banner, so asking costs no request of its own. Only the Settings card
// needs the full registry (the layer that decided each state, whether a pin
// holds it), and that is `GET /daemon/features`.
//
// A switch invalidates the status as well as the list, so the sidebar entry
// appears or leaves on the next render rather than on the next 30-second poll
// (spec experimental-features "List and switch the features on the General
// tab").
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { daemonFeaturesKey, daemonStatusKey } from "@/lib/api/queryKeys";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";

/** The registered experimental features. The daemon's registry is the source
 *  of truth; this union is only what the web UI's own gates name. */
export type FeatureKey = "vault_sync" | "knowledge" | "memory";

export type Feature = components["schemas"]["FeatureOut"];
export type FeatureList = components["schemas"]["FeatureListOut"];
type DaemonStatus = components["schemas"]["DaemonStatusOut"];

/**
 * Whether `key` is switched on: `true` / `false` once the daemon has answered,
 * `undefined` while it has not (still loading, or unreachable).
 *
 * `undefined` is its own answer rather than a guess. Guessing "on" flashes a
 * stable build's switched-off entries into the sidebar for a frame; guessing
 * "off" flashes a notice over a page that is about to load. Callers decide
 * what "not known yet" looks like — the sidebar leaves the entry out, a gated
 * page shows its loading fallback, a query waits.
 *
 * A daemon that answers without a `features` map predates the gates and so
 * has none: everything it serves is on.
 */
export function useFeatureEnabled(key: FeatureKey): boolean | undefined {
  const { data } = useDaemonStatus();
  if (!data) return undefined;
  return data.features?.[key] ?? true;
}

/** The registry with each feature's state and the layer that decided it. */
export function useFeatureList() {
  return useQuery({
    queryKey: daemonFeaturesKey,
    queryFn: async (): Promise<FeatureList> => {
      const { data, error } = await getApiClient().GET("/daemon/features");
      if (error) throwApiError(error, "INTERNAL_ERROR", "features failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty features response");
      return data;
    },
  });
}

/** Switch one feature on or off on this machine. */
export function useSetFeature() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, enabled }: { key: string; enabled: boolean }): Promise<Feature> => {
      const { data, error } = await getApiClient().PUT("/daemon/features/{key}", {
        params: { path: { key } },
        body: { enabled },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "feature update failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty feature response");
      return data;
    },
    onSuccess: (fresh) => {
      // Seed both caches from what the daemon says is true now, so the card
      // and the sidebar move together in this render, then refetch the status
      // to pick up anything else the switch changed.
      qc.setQueryData<FeatureList>(daemonFeaturesKey, (prev) =>
        prev
          ? { ...prev, features: prev.features.map((f) => (f.key === fresh.key ? fresh : f)) }
          : prev,
      );
      qc.setQueryData<DaemonStatus>(daemonStatusKey, (prev) =>
        prev ? { ...prev, features: { ...prev.features, [fresh.key]: fresh.enabled } } : prev,
      );
      void qc.invalidateQueries({ queryKey: daemonStatusKey });
    },
    // A refused write (a pin, a daemon that went away) may still mean the
    // cached list is stale — a pin is visible only on the next read.
    onError: () => void qc.invalidateQueries({ queryKey: daemonFeaturesKey }),
  });
}
