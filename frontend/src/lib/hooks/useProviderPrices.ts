// frontend/src/lib/hooks/useProviderPrices.ts — prices and the proxy route (spec provider-switching).
//
// Model prices resolve on the daemon (You set → the provider's own API → the
// bundled list), and so do context windows (You set → the endpoint → the
// bundled list); an agent's route names the provider it runs on.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { priceListKey, providersApi } from "@/lib/api/providers";
import { proxyAddress, proxyApi, proxyStatusKey } from "@/lib/api/proxy";
import { providerPricesKey } from "@/lib/api/queryKeys";

/** Each of `models`' price on the provider; refetched after every listing. */
export function useModelPrices(uid: string, models: readonly string[], listedAt: number) {
  return useQuery({
    queryKey: providerPricesKey(uid, models, listedAt),
    queryFn: async () => (await providersApi.prices(uid, [...models])).prices,
    enabled: uid !== "" && models.length > 0,
    placeholderData: (previous) => previous,
  });
}

/** Each of `models`' context window on the provider (you set → endpoint →
 *  bundled list); refetched after every listing, like prices. */
export function useModelWindows(uid: string, models: readonly string[], listedAt: number) {
  return useQuery({
    // Under "providers" so saving a provider refetches it, as prices are
    // (kept here: queryKeys.ts is at its size limit).
    queryKey: ["providers", uid, "windows", models, listedAt] as const,
    queryFn: async () => (await providersApi.windows(uid, [...models])).windows,
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

/** The proxy's address, for "Agents reach it through Coffer's proxy · 127.0.0.1:38471". */
export function useProxyAddress(): string {
  const status = useQuery({
    queryKey: proxyStatusKey,
    queryFn: () => proxyApi.status(),
    staleTime: 60_000,
  });
  return proxyAddress(status.data?.port);
}
