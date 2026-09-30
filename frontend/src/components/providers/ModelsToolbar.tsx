// src/components/providers/ModelsToolbar.tsx — the Models section's search, type filter, "Listed … ago" and Refresh.
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, RefreshCw } from "lucide-react";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import type { Modality } from "@/lib/api/providers";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { cn } from "@/lib/utils";

interface Props {
  query: string;
  onQuery: (q: string) => void;
  types: readonly Modality[];
  type: Modality | "all";
  onType: (t: Modality | "all") => void;
  endpoint: UseQueryResult<EndpointModelsOut>;
}

export function ModelsToolbar({ query, onQuery, types, type, onType, endpoint }: Props) {
  const { t, i18n } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SearchInput
        value={query}
        onChange={onQuery}
        placeholder={t("providers.models.search")}
        ariaLabel={t("providers.models.search")}
        className="w-56"
      />
      <div role="group" aria-label={t("providers.models.typeFilter")} className="flex gap-1">
        {(["all", ...types] as const).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={type === m}
            onClick={() => onType(m)}
            className={cn(
              "h-7 rounded-md px-2.5 text-xs font-label outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              type === m
                ? "bg-surface-selected text-text"
                : "text-text-muted hover:bg-surface-hover",
            )}
          >
            {m === "all" ? t("providers.models.allTypes") : t(`providers.modalities.${m}`)}
          </button>
        ))}
      </div>
      <span className="ml-auto flex items-center gap-2 text-xs text-text-muted">
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
        <Button
          variant="outline"
          size="sm"
          onClick={() => void endpoint.refetch()}
          disabled={endpoint.isFetching}
        >
          <RefreshCw aria-hidden /> {t("providers.models.refresh")}
        </Button>
      </span>
    </div>
  );
}
