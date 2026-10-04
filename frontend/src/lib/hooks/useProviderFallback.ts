// frontend/src/lib/hooks/useProviderFallback.ts — prices, list order and the proxy route (spec provider-switching).
//
// Model prices resolve on the daemon (You set → the provider's own API → the
// bundled list); the list order is fallback priority and is saved as a whole;
// an agent's route names the provider it runs on and the ones tried next.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { priceListKey, providersApi, type Provider } from "@/lib/api/providers";
import { proxyAddress, proxyApi, proxyRouteKey, proxyStatusKey } from "@/lib/api/proxy";
import { providerPricesKey, providersKey } from "@/lib/api/queryKeys";

/** Each of `models`' price on the provider; refetched after every listing. */
export function useModelPrices(uid: string, models: readonly string[], listedAt: number) {
  return useQuery({
    queryKey: providerPricesKey(uid, models, listedAt),
    queryFn: async () => (await providersApi.prices(uid, [...models])).prices,
    enabled: uid !== "" && models.length > 0,
    placeholderData: (previous) => previous,
  });
}

/** The price list in use and its daily refresh (Settings › General, Usage). */
export function usePriceList() {
  return useQuery({
    queryKey: priceListKey,
    queryFn: () => providersApi.priceList(),
    staleTime: 60_000,
  });
}

export function useSetPriceRefresh() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (refresh: boolean) => providersApi.setPriceRefresh(refresh),
    onSuccess: (doc) => qc.setQueryData(priceListKey, doc),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Save a new list order. Optimistic: the list moves at once and moves back
 *  if the daemon refuses. */
export function useReorderProviders() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (uids: string[]) => providersApi.reorder(uids),
    onMutate: async (uids) => {
      await qc.cancelQueries({ queryKey: providersKey, exact: true });
      const before = qc.getQueryData<Provider[]>(providersKey);
      if (before) {
        const byUid = new Map(before.map((p) => [p.uid, p]));
        qc.setQueryData<Provider[]>(
          providersKey,
          uids.map((u) => byUid.get(u)).filter((p): p is Provider => p !== undefined),
        );
      }
      return { before };
    },
    onError: (error, _uids, ctx) => {
      if (ctx?.before) qc.setQueryData(providersKey, ctx.before);
      toast.error(translateApiError(t, error));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: providersKey }),
  });
}

/** The agent's provider and its fallbacks for `model`, as the proxy serves them. */
export function useProxyRoute(agentUid: string, model: string | null, enabled = true) {
  return useQuery({
    queryKey: proxyRouteKey(agentUid, model),
    queryFn: () => proxyApi.route(agentUid, model),
    enabled: enabled && agentUid !== "",
  });
}

/** The proxy's address, for "Agents reach it through Coffer's proxy · 127.0.0.1:38471". */
export function useProxyAddress(): string {
  const status = useQuery({
    queryKey: proxyStatusKey,
    queryFn: () => proxyApi.status(),
    staleTime: 60_000,
  });
  return proxyAddress(status.data?.port);
}
