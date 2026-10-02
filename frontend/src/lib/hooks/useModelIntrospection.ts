// frontend/src/lib/hooks/useModelIntrospection.ts
//
// Provider introspection (specs channels and knowledge): list a provider's models + test a
// connection, so the model forms offer a fetched fixed list (no free-text
// entry, spec provider-switching "Choose a model from a fixed list") and a
// Test button — DevPilot-style. Requests go through the typed client's
// `modelProbeApi` (.agents/frontend.md §4).
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  type EndpointModelsOut,
  type ListModelsIn,
  modelProbeApi,
  type TestConnectionIn,
} from "@/lib/api/providers";
import { endpointModelsKey } from "@/lib/api/queryKeys";

export type { EndpointModelsOut };

/** List a provider's models. Empty list + message → the surface shows why. */
export function useListProviderModels() {
  return useMutation({ mutationFn: (p: ListModelsIn) => modelProbeApi.list(p) });
}

/** The model ids an endpoint itself serves, as a QUERY rather than the mutation
 *  above: a surface whose whole job is to show that list (the connection detail
 *  page) should have it on open, not behind a button, and a query is what gives
 *  it the loading / error / refetch states that makes a failed probe visible and
 *  retryable.
 *
 *  The key deliberately does NOT extend ``["providers", uid]``: every
 *  connection mutation invalidates that subtree, so ticking one model on would
 *  re-probe the remote endpoint — a network round trip per click. This list
 *  changes when the ENDPOINT changes, not when our curation does.
 *
 *  `retry: false` because a wrong key or an unreachable endpoint is a real
 *  answer the user must see, not a blip worth three silent attempts.
 *
 *  `endpointModelsKey` lives in `lib/api/queryKeys.ts` with every other key. */
export function useEndpointModels(uid: string, probe: ListModelsIn) {
  return useQuery({
    queryKey: endpointModelsKey(uid),
    queryFn: () => modelProbeApi.list(probe),
    enabled: uid !== "",
    retry: false,
    refetchOnWindowFocus: false,
    // The tab this renders in unmounts when the user switches away, so without a
    // stale window every flick back to it would re-probe the vendor. Once per
    // visit to the page is what "listed when you open it" means; the Retry
    // button is there for when the user wants it asked again.
    staleTime: 5 * 60 * 1000,
  });
}

/** Probe a chat provider with a minimal request. */
export function useTestConnection() {
  return useMutation({ mutationFn: (p: TestConnectionIn) => modelProbeApi.test(p) });
}
