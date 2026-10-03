// src/components/providers/ModelsRefresh.tsx — the Models title's right side: "Listed 2 min ago" (or "Listing failed · last listed …") and Refresh.
//
// A failed listing says so here, in red, with the day it last worked — the
// box under the title does not carry a Retry of its own.
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, RefreshCw } from "lucide-react";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { Button } from "@/components/ui/button";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { formatDay } from "@/lib/time";

interface Props {
  endpoint: UseQueryResult<EndpointModelsOut>;
  failed: boolean;
  /** When the listing last worked (ms epoch), if it ever did in this session. */
  lastListedAt: number | null;
}

export function ModelsRefresh({ endpoint, failed, lastListedAt }: Props) {
  const { t, i18n } = useTranslation();
  const ago = (ms: number) => formatRelativeTime(new Date(ms).toISOString(), i18n.language);
  return (
    <>
      <span className="text-xs text-text-muted">
        {endpoint.isFetching ? (
          <span role="status" className="inline-flex items-center gap-1.5">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            {t("providers.models.listing")}
          </span>
        ) : failed ? (
          <>
            <span className="text-danger">{t("providers.models.listingFailed")}</span>
            {lastListedAt
              ? ` · ${t("providers.models.lastListed", { date: formatDay(new Date(lastListedAt), i18n.language) })}`
              : ""}
          </>
        ) : endpoint.dataUpdatedAt ? (
          t("providers.models.listedAgo", { ago: ago(endpoint.dataUpdatedAt) })
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
