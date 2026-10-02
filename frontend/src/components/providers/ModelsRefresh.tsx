// src/components/providers/ModelsRefresh.tsx — the Models card header's "Listed … ago" and Refresh.
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, RefreshCw } from "lucide-react";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { Button } from "@/components/ui/button";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";

export function ModelsRefresh({ endpoint }: { endpoint: UseQueryResult<EndpointModelsOut> }) {
  const { t, i18n } = useTranslation();
  return (
    <>
      <span className="text-xs text-text-muted">
        {endpoint.isFetching ? (
          <span role="status" className="inline-flex items-center gap-1.5">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            {t("providers.models.listing")}
          </span>
        ) : endpoint.dataUpdatedAt ? (
          t("providers.models.listedAgo", {
            ago: formatRelativeTime(new Date(endpoint.dataUpdatedAt).toISOString(), i18n.language),
          })
        ) : null}
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={() => void endpoint.refetch()}
        disabled={endpoint.isFetching}
      >
        <RefreshCw aria-hidden /> {t("providers.models.refresh")}
      </Button>
    </>
  );
}
