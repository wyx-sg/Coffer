// frontend/src/lib/hooks/useFeatures.ts
//
// The experimental features (spec experimental-features): which of them are
// switched on on this machine, and the switch itself. The two keys are named
// in `lib/features.ts`; the daemon says what state each is in.
//
// Two reads, on purpose. Every surface that only needs "is it on?" — the
// sidebar, the gated routes, a query that belongs to a feature — reads the
// `features` map off `GET /daemon/status`, which the shell already polls for the
// offline banner, so asking costs no request of its own. Only the Settings Features
// tab needs the full registry (the layer that decided each state, whether a pin
// holds it), and that is `GET /daemon/features`.
//
// A switch invalidates the status as well as the list, so the sidebar entry
// appears or leaves on the next render rather than on the next 30-second poll.
// A switched-off feature is absent from the UI, not announced (spec
// experimental-features).
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { featuresApi, type Feature, type FeatureList } from "@/lib/api/features";
import type { components } from "@/lib/api/types";
import { daemonFeaturesKey, daemonStatusKey } from "@/lib/api/queryKeys";
import { featureOfKind, type FeatureKey } from "@/lib/features";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";

export type { FeatureKey };

export type { Feature };
type DaemonStatus = components["schemas"]["DaemonStatusOut"];

/**
 * Whether `key` is switched on: `true` / `false` once the daemon has answered,
 * `undefined` while it has not (still loading, or unreachable).
 *
 * `undefined` is its own answer rather than a guess. Guessing "on" flashes a
 * switched-off entry into the sidebar for a frame; guessing "off" flashes the
 * not-found page over a page that is about to load. Callers decide
 * what "not known yet" looks like — the sidebar leaves the entry out, a gated
 * page shows its loading fallback, a query waits.
 */
export function useFeatureEnabled(key: FeatureKey): boolean | undefined {
  const { data } = useDaemonStatus();
  if (!data) return undefined;
  return data.features[key] === true;
}

/**
 * Every registered feature's state, for a surface that filters many entries by
 * whichever feature each one carries: `null` while the daemon has not answered.
 * A key absent from the map is not registered, so it reads as off.
 */
export function useFeatureMap(): Record<string, boolean> | null {
  const { data } = useDaemonStatus();
  if (!data) return null;
  return data.features;
}

/** Whether an entry carrying `feature` is shown under `map`: an entry with no
 *  feature always is; one with a feature only once the daemon says it is on. */
export function isFeatureOn(
  map: Record<string, boolean> | null,
  feature: FeatureKey | undefined,
): boolean {
  if (feature === undefined) return true;
  if (map === null) return false;
  return map[feature] === true;
}

/** Whether the page of a resource kind exists: a surface that links to a
 *  resource (a secret's citers, an audit record) leaves the link out when the
 *  kind's feature is off, so it never points at a not-found page. */
export function useKindPageOpen(): (kind: string) => boolean {
  const map = useFeatureMap();
  return (kind) => isFeatureOn(map, featureOfKind(kind));
}

/** The registry with each feature's state and the layer that decided it. */
export function useFeatureList() {
  return useQuery({
    queryKey: daemonFeaturesKey,
    queryFn: featuresApi.list,
  });
}

/** Seed both caches from what the daemon says is true now, so the Features tab
 *  and the sidebar move together in this render, then refetch the status to
 *  pick up anything else the switch changed. */
function seedFeature(qc: QueryClient, fresh: Feature) {
  qc.setQueryData<FeatureList>(daemonFeaturesKey, (prev) =>
    prev
      ? { ...prev, features: prev.features.map((f) => (f.key === fresh.key ? fresh : f)) }
      : prev,
  );
  qc.setQueryData<DaemonStatus>(daemonStatusKey, (prev) =>
    prev ? { ...prev, features: { ...prev.features, [fresh.key]: fresh.enabled } } : prev,
  );
  void qc.invalidateQueries({ queryKey: daemonStatusKey });
}

/** Switch one feature on or off on this machine. */
export function useSetFeature() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      featuresApi.set(key, enabled),
    onSuccess: (fresh) => seedFeature(qc, fresh),
    // A refused write (a pin, a daemon that went away) may still mean the
    // cached list is stale — a pin is visible only on the next read.
    onError: () => void qc.invalidateQueries({ queryKey: daemonFeaturesKey }),
  });
}

/** Forget this machine's setting, so the feature is off by default again. */
export function useResetFeature() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => featuresApi.reset(key),
    onSuccess: (fresh) => seedFeature(qc, fresh),
    onError: () => void qc.invalidateQueries({ queryKey: daemonFeaturesKey }),
  });
}
